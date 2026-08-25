"""
Fon Takip Paneli — gun ici tahmin + gun sonu resmi TEFAS verisi (v3)

Yenilikler:
- TEFAS istekleri cerezli oturumla yapilir (once sayfa ziyareti, sonra veri).
- tefas.gov.tr olmazsa fundturkey.com.tr denenir.
- TEFAS hic ulasilamasa bile hisse sepetli fonlarin ~tahminleri gosterilir.
- Kenar cubugunda baglanti durumu gorunur.

Kurulum:  pip install streamlit pandas requests yfinance streamlit-autorefresh
Calistir: streamlit run fon_paneli.py
"""

import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

FONLAR = ["TLY", "THF", "DOH", "TP2", "PRY", "PNU"]
GUN_ADLARI = {0: "Pzt", 1: "Sali", 2: "Cars", 3: "Pers", 4: "Cuma"}

# Aylik KAP raporlarindan hisse agirliklari (%) — her ay guncelleyin
SEPETLER = {
    "TLY": {"OZATD": 14.3, "DSTKF": 14.0, "TEHOL": 9.2, "PEKGY": 8.8,
            "TERA": 4.1, "TRHOL": 4.0, "ALKLC": 1.9, "BIGEN": 1.6,
            "ANELE": 1.0, "SELEC": 1.0},
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
MEVDUAT_BENZERI = ["TP2", "PRY", "PNU"]  # dunku resmi oran = bugunun tahmini

st.set_page_config(page_title="Fon Takip", page_icon="📊", layout="wide")
st.sidebar.header("Ayarlar")
aralik = st.sidebar.slider("Yenileme araligi (dakika)", 1, 30, 3)
st_autorefresh(interval=aralik * 60 * 1000, key="oto_yenile")

# ----------------- Veri kaynaklari: FonParam (acik API) + TEFAS yedek -----------------
KAYNAKLAR = [
    ("https://www.tefas.gov.tr", "tefas.gov.tr"),
    ("https://www.fundturkey.com.tr", "fundturkey.com.tr"),
]
TARAYICI = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

def _fonparam(kod, gun):
    """FonParam acik API'si (TEFAS verisinin yurt disindan erisilebilir aynasi)."""
    bitis = datetime.now()
    baslangic = bitis - timedelta(days=gun)
    r = requests.get(
        f"https://fonparam.apimapi.net/funds/{kod}/historical",
        params={"start_date": baslangic.strftime("%Y-%m-%d"),
                "end_date": bitis.strftime("%Y-%m-%d")},
        headers={"User-Agent": TARAYICI["User-Agent"]}, timeout=10)
    veri = r.json()
    if isinstance(veri, dict):  # {data: [...]} sarmali olabilir
        veri = veri.get("data", [])
    if not veri:
        return None
    t = pd.DataFrame(veri).rename(columns={
        "date": "TARIH", "value": "FIYAT",
        "investor_count": "KISISAYISI", "aum": "PORTFOYBUYUKLUK"})
    t["TARIH"] = pd.to_datetime(t["TARIH"])
    for k in ["FIYAT", "KISISAYISI", "PORTFOYBUYUKLUK"]:
        if k not in t:
            t[k] = None
        t[k] = pd.to_numeric(t[k], errors="coerce")
    t = t.sort_values("TARIH").reset_index(drop=True)
    t["Degisim"] = t["FIYAT"].pct_change() * 100
    return t

def _tefas(kod, gun, site):
    bitis = datetime.now()
    baslangic = bitis - timedelta(days=gun)
    oturum = requests.Session()
    oturum.headers.update(TARAYICI)
    oturum.get(f"{site}/TarihselVeriler.aspx", timeout=10)
    r = oturum.post(f"{site}/api/DB/BindHistoryInfo",
                    data={"fontip": "YAT", "sfontur": "", "fonkod": kod,
                          "fongrup": "",
                          "bastarih": baslangic.strftime("%d.%m.%Y"),
                          "bittarih": bitis.strftime("%d.%m.%Y"),
                          "fonturkod": "", "fonunvantip": ""},
                    headers={"Origin": site,
                             "Referer": f"{site}/TarihselVeriler.aspx"},
                    timeout=10)
    t = pd.DataFrame(r.json()["data"])
    if t.empty:
        return None
    t["TARIH"] = pd.to_datetime(t["TARIH"].astype("int64"), unit="ms")
    for k in ["FIYAT", "KISISAYISI", "PORTFOYBUYUKLUK"]:
        t[k] = pd.to_numeric(t[k], errors="coerce")
    t = t.sort_values("TARIH").reset_index(drop=True)
    t["Degisim"] = t["FIYAT"].pct_change() * 100
    return t

@st.cache_data(ttl=300, show_spinner=False)
def fon_gecmisi(kod, gun=21):
    """Once FonParam (erisime acik), olmazsa TEFAS/fundturkey."""
    try:
        t = _fonparam(kod, gun)
        if t is not None and len(t) >= 2:
            return t, "FonParam"
    except Exception:
        pass
    for site, ad in KAYNAKLAR:
        try:
            t = _tefas(kod, gun, site)
            if t is not None and len(t) >= 2:
                return t, ad
        except Exception:
            continue
    return None, None

@st.cache_data(ttl=120, show_spinner=False)
def sepet_tahmini(kod):
    """Sepet hisselerinin anlik hareketinden gun ici tahmin (%)."""
    sepet = SEPETLER.get(kod)
    if not sepet:
        return None
    toplam, kapsanan = 0.0, 0.0
    for hisse, agirlik in sepet.items():
        try:
            df = yf.download(f"{hisse}.IS", period="5d", interval="1d",
                             progress=False, auto_adjust=True)
            k = df["Close"].squeeze()
            if len(k) < 2:
                continue
            degisim = (float(k.iloc[-1]) / float(k.iloc[-2]) - 1) * 100
            toplam += agirlik / 100 * degisim
            kapsanan += agirlik
        except Exception:
            continue
    return toplam if kapsanan >= 20 else None

def tr_sayi(deger, ondalik=0):
    if pd.isna(deger):
        return "—"
    s = f"{deger:,.{ondalik}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def yuzde_str(deger, tahmin=False):
    if deger is None or pd.isna(deger):
        return "—"
    return f"{'~' if tahmin else ''}{deger:+.2f}".replace(".", ",")

# ----------------- Tabloyu kur -----------------
bugun = datetime.now().date()
pazartesi = bugun - timedelta(days=bugun.weekday())
satirlar, kaynaklar, tefas_yok = [], set(), 0

for kod in FONLAR:
    t, kaynak = fon_gecmisi(kod)
    tahmin = sepet_tahmini(kod)  # TEFAS'tan bagimsiz calisir

    if t is None:
        tefas_yok += 1
        satir = {"Fon": kod, "Fiyat (TL)": "—",
                 "Gunluk %": yuzde_str(tahmin, tahmin=True)}
        for gun_no, ad in GUN_ADLARI.items():
            hedef = pazartesi + timedelta(days=gun_no)
            satir[ad] = yuzde_str(tahmin, True) if hedef == bugun else "—"
        satir.update({"Yatirimci": "—", "Toplam Tutar (TL)": "—"})
        satirlar.append(satir)
        continue

    kaynaklar.add(kaynak)
    son = t.iloc[-1]
    bugun_resmi_var = (son["TARIH"].date() == bugun)
    if tahmin is None and not bugun_resmi_var and kod in MEVDUAT_BENZERI:
        tahmin = float(son["Degisim"])

    satir = {"Fon": kod,
             "Fiyat (TL)": tr_sayi(son["FIYAT"], 4 if son["FIYAT"] < 10 else 2)}
    if bugun_resmi_var:
        satir["Gunluk %"] = yuzde_str(float(son["Degisim"]))
    elif tahmin is not None:
        satir["Gunluk %"] = yuzde_str(tahmin, tahmin=True)
    else:
        satir["Gunluk %"] = yuzde_str(float(son["Degisim"]))

    for gun_no, ad in GUN_ADLARI.items():
        hedef = pazartesi + timedelta(days=gun_no)
        eslesen = t[t["TARIH"].dt.date == hedef]
        if not eslesen.empty:
            satir[ad] = yuzde_str(float(eslesen["Degisim"].iloc[0]))
        elif hedef == bugun and tahmin is not None:
            satir[ad] = yuzde_str(tahmin, tahmin=True)
        else:
            satir[ad] = "—"

    satir["Yatirimci"] = tr_sayi(son["KISISAYISI"])
    satir["Toplam Tutar (TL)"] = tr_sayi(son["PORTFOYBUYUKLUK"], 2)
    satirlar.append(satir)

df = pd.DataFrame(satirlar)

# ----------------- Gorunum -----------------
st.title("📊 Fon Takip Paneli")
st.caption(f"Son kontrol: {datetime.now():%d.%m.%Y %H:%M} | ~ = gun ici tahmin "
           "(hisse hareketlerinden, ~15 dk gecikmeli); resmi fiyat aksam "
           "TEFAS'ta kesinlesir. Yatirim tavsiyesi degildir.")

if tefas_yok == len(FONLAR):
    st.error("TEFAS resmi verilerine su an ulasilamiyor; sadece ~ isaretli gun "
             "ici tahminler gosteriliyor. TEFAS yurt disi sunuculari "
             "engelleyebiliyor — panel her yenilemede tekrar dener.")
elif tefas_yok:
    st.warning(f"{tefas_yok} fonun resmi verisi alinamadi; tahminler ve "
               "digerleri gosteriliyor.")

st.sidebar.caption("Resmi veri kaynagi: "
                   + (", ".join(sorted(kaynaklar)) if kaynaklar else "ulasilamiyor")
                   + " | Tahmin kaynagi: Yahoo Finance")

def renk(v):
    if isinstance(v, str) and v not in ("—", ""):
        try:
            sayi = float(v.replace("~", "").replace(",", "."))
            stil = "font-style: italic; " if v.startswith("~") else ""
            if sayi > 0:
                return stil + "color: #2e7d32; font-weight: 600"
            if sayi < 0:
                return stil + "color: #c62828; font-weight: 600"
        except ValueError:
            pass
    return ""

yuzde_kolonlari = ["Gunluk %"] + list(GUN_ADLARI.values())
st.dataframe(df.style.map(renk, subset=yuzde_kolonlari),
             use_container_width=True, hide_index=True,
             height=40 * len(FONLAR) + 60)
