"""
alarm_kontrol.py v2 — WhatsApp fon alarmlari (GitHub Actions)

Yenilikler:
- FonParam resmi adresi (api.fonparam.com) + eski adres yedegi
- Fon bazli hata yakalama: tek fon patlasa da mesaj gider
- Karne sismografi: tahmin-resmi sapmasi aniden buyurse "sepet kaymis" alarmi
- Sepetler aylik KAP raporundan otomatik cekilir (olmazsa yedek liste)

Kullanim:  python alarm_kontrol.py [kontrol|ozet]
Secrets:   WHATSAPP_PHONE, CALLMEBOT_APIKEY
"""

import os
import io
import re
import sys
import json
import urllib.parse
from datetime import datetime, timedelta

import requests
import pandas as pd
import yfinance as yf

FONLAR = ["TLY", "THF", "DOH", "TP2", "PRY", "PNU"]
YEDEK_SEPETLER = {
    "TLY": {"OZATD": 14.3, "DSTKF": 14.0, "TEHOL": 9.2, "PEKGY": 8.8,
            "TERA": 4.1, "TRHOL": 4.0, "ALKLC": 1.9, "BIGEN": 1.6,
            "ANELE": 1.0, "SELEC": 1.0, "SVGYO": 0.5, "HEDEF": 0.5,
            "MANAS": 0.5, "EUPWR": 0.5, "TMPOL": 0.5},
    "THF": {"OZATD": 7.2, "ASELS": 7.2, "TERA": 6.7, "TEHOL": 5.6,
            "KARCL": 4.7, "MANAS": 4.3, "TRHOL": 4.1, "YKBNK": 3.8,
            "THYAO": 3.7, "BRSAN": 3.6, "ORZAX": 3.6, "KGYO": 3.6,
            "NETCD": 3.3, "BARMA": 3.1, "MCARD": 3.1, "ANELE": 2.8,
            "HALKB": 2.6, "GLRMK": 2.4, "EGEGY": 2.4, "SVGYO": 2.1,
            "TUPRS": 2.1},
    "DOH": {"LIDER": 19.0, "TERA": 18.9, "TEHOL": 10.6, "ANELE": 7.4,
            "NETCD": 7.0, "TRHOL": 6.8, "BARMA": 5.7, "ASELS": 5.7,
            "OZATD": 2.1},
}
RISKLER = {"TLY": 7, "THF": 6, "DOH": 6, "TP2": 1, "PRY": 1, "PNU": 1}
ESIK = {7: -3.5, 6: -2.5, 5: -2.5, 4: -1.5, 3: -1.5, 2: -0.1, 1: -0.1}
DURUM_DOSYASI = "alarm_durum.json"
FONPARAM_ADRESLER = ["https://api.fonparam.com",
                     "https://fonparam.apimapi.net"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
KARA_LISTE = {"TOPLAM", "TARIH", "FONUN", "HISSE", "PAYLAR", "BIST", "VADELI",
              "TAKAS", "REPO", "DIGER", "TERS", "DEVLET", "OZEL", "YATIRIM",
              "MEVDUAT", "KATILMA", "SAYFA", "SANAYI", "ENERJI", "GIDA",
              "DEMIR", "CELIK", "BANKA", "METAL", "TARIM", "INSAAT", "TURIZM"}

def simdi_tr():
    return datetime.utcnow() + timedelta(hours=3)

# ---------- Sepetler: once KAP raporundan otomatik, olmazsa yedek ----------
def sepet_otomatik(kod):
    try:
        import pdfplumber
    except Exception:
        return None
    simdi = simdi_tr()
    for geri in range(2):
        ay, yil = simdi.month - geri, simdi.year
        if ay < 1:
            ay, yil = ay + 12, yil - 1
        try:
            r = requests.get(
                "https://storage.fintables.com/media/uploads/"
                f"kap-attachments/{kod}_{yil}.{ay:02d}.pdf",
                headers=UA, timeout=8)
            if r.status_code != 200 or r.content[:4] != b"%PDF":
                continue
            metin = ""
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                for sayfa in pdf.pages:
                    metin += (sayfa.extract_text() or "") + "\n"
            ag = {}
            for satir in metin.split("\n"):
                m = re.match(r"^([A-Z]{4,6})\s", satir)
                if not m or m.group(1) in KARA_LISTE:
                    continue
                yuzdeler = re.findall(r"(\d{1,2},\d{2})", satir)
                if not yuzdeler:
                    continue
                try:
                    w = float(yuzdeler[-1].replace(",", "."))
                except ValueError:
                    continue
                if 0 < w <= 60:
                    ag[m.group(1)] = ag.get(m.group(1), 0) + w
            if len(ag) >= 3 and 25 <= sum(ag.values()) <= 110:
                return ag
        except Exception:
            continue
    return None

def sepetleri_kur():
    sepetler = {}
    for kod, yedek in YEDEK_SEPETLER.items():
        oto = sepet_otomatik(kod)
        sepetler[kod] = oto if oto else dict(yedek)
    return sepetler

# ---------- Veri ----------
def fon_gecmisi(kod, gun=45):
    bitis = datetime.now()
    for adres in FONPARAM_ADRESLER:
        try:
            r = requests.get(
                f"{adres}/funds/{kod}/historical",
                params={"start_date": (bitis - timedelta(days=gun)).strftime("%Y-%m-%d"),
                        "end_date": bitis.strftime("%Y-%m-%d")},
                headers=UA, timeout=12)
            if r.status_code != 200:
                continue
            veri = r.json()
            if isinstance(veri, dict):
                veri = veri.get("data", [])
            t = pd.DataFrame(veri)
            if t.empty:
                continue
            t = t.rename(columns={"date": "TARIH", "value": "FIYAT",
                                  "investor_count": "KISI", "aum": "TUTAR"})
            t["TARIH"] = pd.to_datetime(t["TARIH"])
            for k in ["FIYAT", "KISI", "TUTAR"]:
                t[k] = pd.to_numeric(t.get(k), errors="coerce")
            t = t.sort_values("TARIH").reset_index(drop=True)
            t["Degisim"] = t["FIYAT"].pct_change() * 100
            return t
        except Exception:
            continue
    return None

def hisse_gecmisi(sepetler):
    """Tum sepet hisselerinin tarih x hisse gunluk % degisim tablosu."""
    semboller = sorted({f"{h}.IS" for s in sepetler.values() for h in s})
    try:
        toplu = yf.download(semboller, period="2mo", interval="1d",
                            progress=False, auto_adjust=True,
                            group_by="ticker", threads=True)
    except Exception:
        return pd.DataFrame()
    seriler = {}
    for sem in semboller:
        try:
            k = toplu[sem]["Close"].dropna()
            if len(k) >= 2:
                seriler[sem[:-3]] = k.pct_change() * 100
        except Exception:
            continue
    deg = pd.DataFrame(seriler)
    if not deg.empty:
        deg.index = pd.to_datetime(deg.index).date
    return deg

def sepet_tahmini(kod, sepetler, deg, tarih=None):
    sepet = sepetler.get(kod)
    if not sepet or deg.empty:
        return None
    if tarih is None:
        satir = deg.iloc[-1]
    elif tarih in deg.index:
        satir = deg.loc[tarih]
    else:
        return None
    toplam = kapsanan = 0.0
    for h, w in sepet.items():
        if h in satir.index and pd.notna(satir[h]):
            toplam += w / 100 * float(satir[h])
            kapsanan += w
    return toplam if kapsanan >= 20 else None

# ---------- WhatsApp ----------
def whatsapp_gonder(metin):
    tel = os.environ.get("WHATSAPP_PHONE", "").strip()
    anahtar = os.environ.get("CALLMEBOT_APIKEY", "").strip()
    if not tel or not anahtar:
        print("HATA: WHATSAPP_PHONE / CALLMEBOT_APIKEY secrets eksik.")
        return False
    try:
        r = requests.get("https://api.callmebot.com/whatsapp.php",
                         params={"phone": tel, "apikey": anahtar,
                                 "text": metin}, timeout=30)
        print("CallMeBot:", r.status_code, r.text[:100])
        return r.status_code == 200
    except Exception as e:
        print("Gonderim hatasi:", e)
        return False

# ---------- Durum (ayni alarm gunde 1 kez) ----------
def durum_oku():
    try:
        with open(DURUM_DOSYASI) as f:
            return json.load(f)
    except Exception:
        return {}

def durum_yaz(durum):
    bugun = simdi_tr().strftime("%Y-%m-%d")
    with open(DURUM_DOSYASI, "w") as f:
        json.dump({bugun: durum.get(bugun, [])}, f)

def gitti(durum, anahtar):
    return anahtar in durum.get(simdi_tr().strftime("%Y-%m-%d"), [])

def isaretle(durum, anahtar):
    durum.setdefault(simdi_tr().strftime("%Y-%m-%d"), []).append(anahtar)

# ---------- Modlar ----------
def alarm_kontrol():
    durum = durum_oku()
    sepetler = sepetleri_kur()
    deg = hisse_gecmisi(sepetler)
    mesajlar = []
    for kod in FONLAR:
        try:
            t = fon_gecmisi(kod)
            esik = ESIK.get(RISKLER.get(kod, 5), -2.0)

            gunluk, kaynak = None, ""
            if t is not None and len(t) >= 2 \
                    and t["TARIH"].iloc[-1].date() == simdi_tr().date():
                gunluk, kaynak = float(t["Degisim"].iloc[-1]), "resmi"
            if gunluk is None:
                th = sepet_tahmini(kod, sepetler, deg)
                if th is not None:
                    gunluk, kaynak = th, "tahmini"

            # 1) Esik alarmi
            if gunluk is not None and gunluk <= esik and not gitti(durum, f"{kod}-esik"):
                mesajlar.append(f"🔴 *{kod}* gunluk {kaynak} %{gunluk:+.2f} — "
                                f"esik (%{esik}) asildi.")
                isaretle(durum, f"{kod}-esik")

            # 2) Taban alarmi (ayarlama haric)
            if kod in sepetler and not deg.empty:
                son_deg = deg.iloc[-1]
                tabanlar = [h for h in sepetler[kod]
                            if h in son_deg.index and pd.notna(son_deg[h])
                            and -10.5 < float(son_deg[h]) <= -9.5]
                if tabanlar and not gitti(durum, f"{kod}-taban"):
                    mesajlar.append(f"🟠 *{kod}* sepetinde taban: "
                                    + ", ".join(tabanlar))
                    isaretle(durum, f"{kod}-taban")

            # 3) Cikis sinyali
            if kod in sepetler and t is not None and len(t) >= 2:
                ky = t["KISI"].iloc[-1] - t["KISI"].iloc[-2]
                kt = t["TUTAR"].iloc[-1] - t["TUTAR"].iloc[-2]
                if pd.notna(ky) and pd.notna(kt) and ky < 0 and kt < 0 \
                        and not gitti(durum, f"{kod}-cikis"):
                    mesajlar.append(f"🟡 *{kod}*: yatirimci ({int(ky):+,}) ve "
                                    f"tutar ({kt/1e9:+.2f} mlr TL) birlikte "
                                    "eksi — cikis sinyali.")
                    isaretle(durum, f"{kod}-cikis")

            # 4) Karne sismografi: sapma aniden buyudu = sepet kaymis olabilir
            if kod in sepetler and t is not None and not deg.empty \
                    and not gitti(durum, f"{kod}-karne"):
                sapmalar = []
                for _, r in t.iterrows():
                    if pd.isna(r["Degisim"]):
                        continue
                    th = sepet_tahmini(kod, sepetler, deg, r["TARIH"].date())
                    if th is not None:
                        sapmalar.append(th - float(r["Degisim"]))
                if len(sapmalar) >= 10:
                    s = pd.Series(sapmalar)
                    son3 = s.tail(3).abs().mean()
                    onceki = s.iloc[:-3].abs().mean()
                    if son3 > 1.0 and son3 > 2 * max(onceki, 0.2):
                        mesajlar.append(
                            f"🟣 *{kod}*: tahmin sapmasi son 3 gunde "
                            f"±{son3:.1f} puana cikti (onceki ±{onceki:.1f}) "
                            "— fon sepetini rapor disinda degistirmis "
                            "olabilir, temkinli izle.")
                        isaretle(durum, f"{kod}-karne")
        except Exception as e:
            print(f"{kod} kontrolunde hata (atlandi): {e}")

    if mesajlar:
        whatsapp_gonder("⚠ *Fon Alarm* (" + simdi_tr().strftime("%d.%m %H:%M")
                        + " TR)\n\n" + "\n\n".join(mesajlar)
                        + "\n\n_Yatirim tavsiyesi degildir._")
    else:
        print("Alarm kosulu yok.")
    durum_yaz(durum)

def gun_sonu_ozet():
    sepetler = sepetleri_kur()
    deg = hisse_gecmisi(sepetler)
    satirlar = []
    for kod in FONLAR:
        try:
            t = fon_gecmisi(kod)
            if t is None or len(t) < 2:
                th = sepet_tahmini(kod, sepetler, deg)
                satirlar.append(f"*{kod}*: ~%{th:+.2f} (tahmini)"
                                if th is not None else f"*{kod}*: veri yok")
                continue
            son = t.iloc[-1]
            if son["TARIH"].date() == simdi_tr().date():
                satirlar.append(f"*{kod}*: %{float(son['Degisim']):+.2f} "
                                f"({float(son['FIYAT']):,.2f} TL)")
            else:
                th = sepet_tahmini(kod, sepetler, deg)
                if th is not None:
                    satirlar.append(f"*{kod}*: ~%{th:+.2f} (tahmini; resmi aksam)")
                else:
                    satirlar.append(f"*{kod}*: %{float(son['Degisim']):+.2f} "
                                    f"({son['TARIH'].strftime('%d.%m')} resmi)")
        except Exception as e:
            satirlar.append(f"*{kod}*: hata ({type(e).__name__})")
    ek = ""
    try:
        if "TLY" in sepetler and not deg.empty:
            son_deg = deg.iloc[-1]
            tly = [(h, float(son_deg[h])) for h in sepetler["TLY"]
                   if h in son_deg.index and pd.notna(son_deg[h])]
            if tly:
                iyi = max(tly, key=lambda x: x[1])
                kotu = min(tly, key=lambda x: x[1])
                ek = (f"\n\nTLY sepeti: en iyi {iyi[0]} %{iyi[1]:+.1f}, "
                      f"en kotu {kotu[0]} %{kotu[1]:+.1f}")
    except Exception:
        pass
    whatsapp_gonder("📊 *Gun Sonu Ozeti* (" + simdi_tr().strftime("%d.%m.%Y")
                    + ")\n\n" + "\n".join(satirlar) + ek
                    + "\n\n_Yatirim tavsiyesi degildir._")

if __name__ == "__main__":
    mod = sys.argv[1] if len(sys.argv) > 1 else "kontrol"
    try:
        gun_sonu_ozet() if mod == "ozet" else alarm_kontrol()
    except Exception as e:
        # Son savunma: script asla sessizce olmesin, log birak
        print("KRITIK HATA:", e)
        raise
