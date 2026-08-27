"""
alarm_kontrol.py — WhatsApp fon alarmlari (GitHub Actions ile calisir)

Kullanim:
  python alarm_kontrol.py          -> alarm kontrolu (esik/taban/cikis)
  python alarm_kontrol.py ozet     -> gun sonu ozet mesaji

Gerekli ortam degiskenleri (GitHub Secrets):
  WHATSAPP_PHONE   : +905xxxxxxxxx (ulke koduyla)
  CALLMEBOT_APIKEY : CallMeBot'un WhatsApp'tan gonderdigi anahtar
"""

import os
import sys
import json
import urllib.parse
from datetime import datetime, timedelta

import requests
import pandas as pd
import yfinance as yf

FONLAR = ["TLY", "THF", "DOH", "TP2", "PRY", "PNU"]
SEPETLER = {
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
# Risk seviyesine gore gunluk dusus alarm esigi (%). Yuksek risk = yuksek
# oynaklik oldugundan esik de yuksek; para fonunda eksi gun basli basina anormal.
ESIK = {7: -3.5, 6: -2.5, 5: -2.5, 4: -1.5, 3: -1.5, 2: -0.1, 1: -0.1}
DURUM_DOSYASI = "alarm_durum.json"

def simdi_tr():
    return datetime.utcnow() + timedelta(hours=3)

# ---------- Veri ----------
def fon_gecmisi(kod, gun=15):
    bitis = datetime.now()
    r = requests.get(
        f"https://fonparam.apimapi.net/funds/{kod}/historical",
        params={"start_date": (bitis - timedelta(days=gun)).strftime("%Y-%m-%d"),
                "end_date": bitis.strftime("%Y-%m-%d")},
        headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    veri = r.json()
    if isinstance(veri, dict):
        veri = veri.get("data", [])
    t = pd.DataFrame(veri)
    if t.empty:
        return None
    t = t.rename(columns={"date": "TARIH", "value": "FIYAT",
                          "investor_count": "KISI", "aum": "TUTAR"})
    t["TARIH"] = pd.to_datetime(t["TARIH"])
    for k in ["FIYAT", "KISI", "TUTAR"]:
        t[k] = pd.to_numeric(t.get(k), errors="coerce")
    t = t.sort_values("TARIH").reset_index(drop=True)
    t["Degisim"] = t["FIYAT"].pct_change() * 100
    return t

def hisse_degisimleri():
    semboller = [f"{h}.IS" for s in SEPETLER.values() for h in s]
    semboller = sorted(set(semboller))
    try:
        toplu = yf.download(semboller, period="5d", interval="1d",
                            progress=False, auto_adjust=True,
                            group_by="ticker", threads=True)
    except Exception:
        return {}
    sonuc = {}
    for sem in semboller:
        try:
            k = toplu[sem]["Close"].dropna()
            if len(k) >= 2:
                sonuc[sem[:-3]] = (float(k.iloc[-1]) / float(k.iloc[-2]) - 1) * 100
        except Exception:
            continue
    return sonuc

def sepet_tahmini(kod, degisimler):
    sepet = SEPETLER.get(kod)
    if not sepet:
        return None
    toplam = kapsanan = 0.0
    for h, w in sepet.items():
        if h in degisimler:
            toplam += w / 100 * degisimler[h]
            kapsanan += w
    return toplam if kapsanan >= 20 else None

# ---------- WhatsApp ----------
def whatsapp_gonder(metin):
    tel = os.environ.get("WHATSAPP_PHONE", "").strip()
    anahtar = os.environ.get("CALLMEBOT_APIKEY", "").strip()
    if not tel or not anahtar:
        print("HATA: WHATSAPP_PHONE / CALLMEBOT_APIKEY secrets tanimli degil.")
        return False
    url = ("https://api.callmebot.com/whatsapp.php?phone=" + urllib.parse.quote(tel)
           + "&apikey=" + urllib.parse.quote(anahtar)
           + "&text=" + urllib.parse.quote(metin))
    try:
        r = requests.get(url, timeout=30)
        print("CallMeBot yaniti:", r.status_code, r.text[:120])
        return r.status_code == 200
    except Exception as e:
        print("Gonderim hatasi:", e)
        return False

# ---------- Durum (ayni alarmi gunde 1 kez gonder) ----------
def durum_oku():
    try:
        with open(DURUM_DOSYASI) as f:
            return json.load(f)
    except Exception:
        return {}

def durum_yaz(durum):
    bugun = simdi_tr().strftime("%Y-%m-%d")
    durum = {bugun: durum.get(bugun, [])}  # eski gunleri temizle
    with open(DURUM_DOSYASI, "w") as f:
        json.dump(durum, f)

def zaten_gitti(durum, anahtar):
    bugun = simdi_tr().strftime("%Y-%m-%d")
    return anahtar in durum.get(bugun, [])

def isaretle(durum, anahtar):
    bugun = simdi_tr().strftime("%Y-%m-%d")
    durum.setdefault(bugun, []).append(anahtar)

# ---------- Modlar ----------
def alarm_kontrol():
    durum = durum_oku()
    degisimler = hisse_degisimleri()
    mesajlar = []
    for kod in FONLAR:
        t = fon_gecmisi(kod)
        risk = RISKLER.get(kod, 5)
        esik = ESIK.get(risk, -2.0)

        # Gunun degeri: resmi varsa o, yoksa sepet tahmini
        gunluk, kaynak = None, ""
        if t is not None and len(t) >= 2:
            if t["TARIH"].iloc[-1].date() == simdi_tr().date():
                gunluk, kaynak = float(t["Degisim"].iloc[-1]), "resmi"
        if gunluk is None:
            th = sepet_tahmini(kod, degisimler)
            if th is not None:
                gunluk, kaynak = th, "tahmini"

        # 1) Risk esigi alarmi
        if gunluk is not None and gunluk <= esik:
            anahtar = f"{kod}-esik"
            if not zaten_gitti(durum, anahtar):
                mesajlar.append(f"🔴 *{kod}* gunluk {kaynak} %{gunluk:+.2f} — "
                                f"risk {risk}/7 esigi (%{esik}) asildi.")
                isaretle(durum, anahtar)

        # 2) Taban alarmi (sepet hisseleri; +-10.5 ustu = fiyat ayarlamasi, sayma)
        tabanlar = [h for h, w in SEPETLER.get(kod, {}).items()
                    if h in degisimler and -10.5 < degisimler[h] <= -9.5]
        if tabanlar:
            anahtar = f"{kod}-taban"
            if not zaten_gitti(durum, anahtar):
                mesajlar.append(f"🟠 *{kod}* sepetinde taban: "
                                + ", ".join(tabanlar)
                                + " — likidite riskine dikkat.")
                isaretle(durum, anahtar)

        # 3) Cikis sinyali: hem yatirimci hem tutar gunluk eksi
        if t is not None and len(t) >= 2:
            ky, kt = t["KISI"].iloc[-1] - t["KISI"].iloc[-2], \
                     t["TUTAR"].iloc[-1] - t["TUTAR"].iloc[-2]
            if pd.notna(ky) and pd.notna(kt) and ky < 0 and kt < 0 \
                    and kod in SEPETLER:
                anahtar = f"{kod}-cikis"
                if not zaten_gitti(durum, anahtar):
                    mesajlar.append(f"🟡 *{kod}*: yatirimci ({int(ky):+,}) ve "
                                    f"tutar ({kt/1e9:+.2f} mlr TL) birlikte "
                                    "eksi — cikis sinyali izlemede.")
                    isaretle(durum, anahtar)

    if mesajlar:
        metin = ("⚠ *Fon Alarm* (" + simdi_tr().strftime("%d.%m %H:%M")
                 + " TR)\n\n" + "\n\n".join(mesajlar)
                 + "\n\n_Yatirim tavsiyesi degildir._")
        whatsapp_gonder(metin)
    else:
        print("Alarm kosulu yok.")
    durum_yaz(durum)

def gun_sonu_ozet():
    degisimler = hisse_degisimleri()
    satirlar = []
    for kod in FONLAR:
        t = fon_gecmisi(kod)
        if t is None or len(t) < 2:
            satirlar.append(f"{kod}: veri yok")
            continue
        son = t.iloc[-1]
        resmi_bugun = son["TARIH"].date() == simdi_tr().date()
        if resmi_bugun:
            satirlar.append(f"*{kod}*: %{float(son['Degisim']):+.2f} "
                            f"({float(son['FIYAT']):,.2f} TL)")
        else:
            th = sepet_tahmini(kod, degisimler)
            if th is not None:
                satirlar.append(f"*{kod}*: ~%{th:+.2f} (tahmini; resmi aksam)")
            else:
                satirlar.append(f"*{kod}*: %{float(son['Degisim']):+.2f} "
                                "(dunun resmi verisi)")
    # TLY sepetinde gunun one cikanlari
    tly = [(h, degisimler[h]) for h in SEPETLER["TLY"] if h in degisimler]
    ek = ""
    if tly:
        en_iyi = max(tly, key=lambda x: x[1])
        en_kotu = min(tly, key=lambda x: x[1])
        ek = (f"\n\nTLY sepetinde: en iyi {en_iyi[0]} %{en_iyi[1]:+.1f}, "
              f"en kotu {en_kotu[0]} %{en_kotu[1]:+.1f}")
    metin = ("📊 *Gun Sonu Ozeti* (" + simdi_tr().strftime("%d.%m.%Y")
             + ")\n\n" + "\n".join(satirlar) + ek
             + "\n\n_Yatirim tavsiyesi degildir._")
    whatsapp_gonder(metin)

if __name__ == "__main__":
    mod = sys.argv[1] if len(sys.argv) > 1 else "kontrol"
    if mod == "ozet":
        gun_sonu_ozet()
    else:
        alarm_kontrol()
