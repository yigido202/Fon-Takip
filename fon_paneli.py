"""
Fon Takip Paneli — gun ici tahmin + gun sonu resmi TEFAS verisi

Tablo: Fon | Fiyat | Gunluk % | Pzt..Cuma | Yatirimci | Toplam Tutar
- Bugunun sutunu gun boyunca ~ isaretli TAHMIN gosterir (fon sepetindeki
  hisselerin anlik hareketinden hesaplanir, ~15 dk gecikmeli).
- TEFAS aksam resmi fiyati aciklayinca tahmin yerini kesin veriye birakir.

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

# --- Gun ici tahmin ayarlari ---------------------------------------------
# Sepet tanimli fonlar: aylik portfoy raporundaki hisse agirliklari (%).
# Rapor her ay yenilenir; buradaki listeyi guncel tutun.
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
# Para piyasasi fonlari: gunluk getirisi cok duzenlidir,
# bugunun tahmini olarak dunku resmi oran kullanilir.
MEVDUAT_BENZERI = ["TP2", "PRY", "PNU"]

st.set_page_config(page_title="Fon Takip", page_icon="📊", layout="wide")
st.sidebar.header("Ayarlar")
aralik = st.sidebar.slider("Yenileme araligi (dakika)", 1, 30, 3)
st_autorefresh(interval=aralik * 60 * 1000, key="oto_yenile")

# --- Veri kaynaklari ------------------------------------------------------
TEFAS_KAYNAKLARI = [
    ("https://www.tefas.gov.tr/api/DB/BindHistoryInfo",
     "https://www.tefas.gov.tr/TarihselVeriler.aspx"),
    ("https://www.fundturkey.com.tr/api/DB/BindHistoryInfo",
     "https://www.fundturkey.com.tr/TarihselVeriler.aspx"),
]

@st.cache_data(ttl=300, show_spinner=False)
def fon_gecmisi(kod, gun=21):
    bitis = datetime.now()
    baslangic = bitis - timedelta(days=gun)
    for url, referer in TEFAS_KAYNAKLARI:
        try:
            r = requests.post(
                url,
                data={"fontip": "YAT", "fonkod": kod,
                      "bastarih": baslangic.strftime("%d.%m.%Y"),
                      "bittarih": bitis.strftime("%d.%m.%Y")},
                headers={"User-Agent": "Mozilla/5.0", "Referer": referer,
                         "Origin": referer.rsplit("/", 1)[0]},
                timeout=12)
            t = pd.DataFrame(r.json()["data"])
            if t.empty:
                continue
            t["TARIH"] = pd.to_datetime(t["TARIH"].astype("int64"), unit="ms")
            for k in ["FIYAT", "KISISAYISI", "PORTFOYBUYUKLUK"]:
                t[k] = pd.to_numeric(t[k], errors="coerce")
            t = t.sort_values("TARIH").reset_index(drop=True)
            t["Degisim"] = t["FIYAT"].pct_change() * 100
            return t
        except Exception:
            continue
    return None

@st.cache_data(ttl=120, show_spinner=False)
def sepet_tahmini(kod):
    """Fon sepetindeki hisselerin anlik degisiminden gun ici tahmin (%)."""
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
    return toplam if kapsanan >= 20 else None  # sepetin cogu geldiyse guven

def tr_sayi(deger, ondalik=0):
    if pd.isna(deger):
        return "—"
    s = f"{deger:,.{ondalik}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def yuzde_str(deger, tahmin=False):
    if deger is None or pd.isna(deger):
        return "—"
    isaret = "~" if tahmin else ""
    return f"{isaret}{deger:+.2f}".replace(".", ",")

# --- Tablo verisini kur ---------------------------------------------------
bugun = datetime.now().date()
pazartesi = bugun - timedelta(days=bugun.weekday())
hata_sayisi = 0
satirlar = []

for kod in FONLAR:
    t = fon_gecmisi(kod)
    if t is None or len(t) < 2:
        hata_sayisi += 1
        satir = {"Fon": kod, "Fiyat (TL)": "—", "Gunluk %": "—"}
        satir.update({ad: "—" for ad in GUN_ADLARI.values()})
        satir.update({"Yatirimci": "—", "Toplam Tutar (TL)": "—"})
        satirlar.append(satir)
        continue

    son = t.iloc[-1]
    satir = {"Fon": kod,
             "Fiyat (TL)": tr_sayi(son["FIYAT"], 4 if son["FIYAT"] < 10 else 2)}

    # Gun ici tahmin (bugunun resmi verisi henuz yoksa kullanilir)
    bugun_resmi_var = (son["TARIH"].date() == bugun)
    tahmin = None
    if not bugun_resmi_var and bugun.weekday() < 5:
        tahmin = sepet_tahmini(kod)
        if tahmin is None and kod in MEVDUAT_BENZERI:
            tahmin = float(son["Degisim"])  # dunku orani bugune tasi

    # Gunluk %: bugun resmi veri varsa o, yoksa tahmin, o da yoksa son resmi
    if bugun_resmi_var:
        satir["Gunluk %"] = yuzde_str(float(son["Degisim"]))
    elif tahmin is not None:
        satir["Gunluk %"] = yuzde_str(tahmin, tahmin=True)
    else:
        satir["Gunluk %"] = yuzde_str(float(son["Degisim"]))

    # Hafta ici gun sutunlari
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

# --- Gorunum --------------------------------------------------------------
st.title("📊 Fon Takip Paneli")
st.caption(f"Son kontrol: {datetime.now():%d.%m.%Y %H:%M} | ~ isareti gun ici "
           "TAHMIN demektir (sepet hisselerinin ~15 dk gecikmeli hareketinden); "
           "resmi fiyat aksam TEFAS'ta aciklaninca kesinlesir. "
           "Yatirim tavsiyesi degildir.")

if hata_sayisi == len(FONLAR):
    st.error("TEFAS'a ulasilamiyor (tefas.gov.tr ve fundturkey.com.tr denendi). "
             "TEFAS yurt disi sunuculari zaman zaman engeller — birkac dakika "
             "sonra otomatik yenilemeyi bekleyin ya da Manage app > Reboot deneyin.")
elif hata_sayisi:
    st.warning(f"{hata_sayisi} fonun verisi su an alinamadi; digerleri guncel.")

def renk(v):
    if isinstance(v, str) and v not in ("—", ""):
        deger = v.replace("~", "").replace(",", ".")
        try:
            sayi = float(deger)
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

st.caption("Sepet tanimli fonlarda (su an: " + ", ".join(SEPETLER)
           + ") gun ici tahmin hisse hareketlerinden hesaplanir. Diger fonlara "
           "tahmin eklemek icin koddaki SEPETLER sozlugune aylik portfoy "
           "raporundaki hisseleri ekleyin. " + ", ".join(MEVDUAT_BENZERI)
           + " icin dunku oran bugune tasinir.")
