"""
Fon Takip Paneli (Streamlit) — TEFAS verili
Tablo: Fon | Fiyat | Gunluk % | Pzt | Sali | Cars | Pers | Cuma | Yatirimci | Toplam Tutar

Kurulum:  pip install streamlit pandas requests streamlit-autorefresh
Calistir: streamlit run fon_paneli.py

Not: TEFAS verileri gun sonunda aciklanir (~1 gun gecikmeli).
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# Takip edilecek fonlar — istedigini ekle/cikar
FONLAR = ["TLY", "THF", "DOH", "TP2", "PRY", "PNU"]
GUN_ADLARI = {0: "Pzt %", 1: "Sali %", 2: "Cars %", 3: "Pers %", 4: "Cuma %"}

st.set_page_config(page_title="Fon Takip", page_icon="📊", layout="wide")

st.sidebar.header("Ayarlar")
aralik = st.sidebar.slider("Yenileme araligi (dakika)", 1, 30, 5)
st_autorefresh(interval=aralik * 60 * 1000, key="oto_yenile")
st.sidebar.caption("TEFAS fon fiyatlari gun sonunda aciklanir; "
                   "gun ici anlik degisim yayinlanmaz.")

@st.cache_data(ttl=300, show_spinner=False)
def fon_gecmisi(kod, gun=21):
    """TEFAS'tan fonun gunluk fiyat/yatirimci/buyukluk gecmisi."""
    bitis = datetime.now()
    baslangic = bitis - timedelta(days=gun)
    r = requests.post(
        "https://www.tefas.gov.tr/api/DB/BindHistoryInfo",
        data={"fontip": "YAT", "fonkod": kod,
              "bastarih": baslangic.strftime("%d.%m.%Y"),
              "bittarih": bitis.strftime("%d.%m.%Y")},
        headers={"User-Agent": "Mozilla/5.0",
                 "Origin": "https://www.tefas.gov.tr",
                 "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx"},
        timeout=15)
    t = pd.DataFrame(r.json()["data"])
    if t.empty:
        return None
    t["TARIH"] = pd.to_datetime(t["TARIH"].astype("int64"), unit="ms")
    for k in ["FIYAT", "KISISAYISI", "PORTFOYBUYUKLUK"]:
        t[k] = pd.to_numeric(t[k], errors="coerce")
    t = t.sort_values("TARIH").reset_index(drop=True)
    t["Degisim"] = t["FIYAT"].pct_change() * 100
    return t

def tr_sayi(deger, ondalik=0):
    """1234567.89 -> '1.234.567,89' (Turk bicimi)"""
    if pd.isna(deger):
        return "—"
    s = f"{deger:,.{ondalik}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def satir_olustur(kod):
    try:
        t = fon_gecmisi(kod)
        if t is None or len(t) < 2:
            raise ValueError("veri yok")
        son = t.iloc[-1]
        satir = {
            "Fon": kod,
            "Fiyat (TL)": tr_sayi(son["FIYAT"], 4 if son["FIYAT"] < 10 else 2),
            "Gunluk %": son["Degisim"],
        }
        # Icinde bulundugumuz haftanin Pazartesi'sinden itibaren gunler
        bugun = datetime.now().date()
        pazartesi = bugun - timedelta(days=bugun.weekday())
        for gun_no, ad in GUN_ADLARI.items():
            hedef = pazartesi + timedelta(days=gun_no)
            eslesen = t[t["TARIH"].dt.date == hedef]
            satir[ad] = float(eslesen["Degisim"].iloc[0]) if not eslesen.empty else None
        satir["Yatirimci"] = tr_sayi(son["KISISAYISI"])
        satir["Toplam Tutar (TL)"] = tr_sayi(son["PORTFOYBUYUKLUK"], 2)
        satir["_veri_tarihi"] = son["TARIH"].date()
        return satir
    except Exception:
        bos = {"Fon": kod, "Fiyat (TL)": "—", "Gunluk %": None}
        bos.update({ad: None for ad in GUN_ADLARI.values()})
        bos.update({"Yatirimci": "—", "Toplam Tutar (TL)": "—", "_veri_tarihi": None})
        return bos

# ----------------- TABLO -----------------
satirlar = [satir_olustur(kod) for kod in FONLAR]
df = pd.DataFrame(satirlar)
veri_tarihi = next((s["_veri_tarihi"] for s in satirlar if s["_veri_tarihi"]), None)
df = df.drop(columns=["_veri_tarihi"])

st.title("📊 Fon Takip Paneli")
st.caption(f"Veri tarihi: {veri_tarihi.strftime('%d.%m.%Y') if veri_tarihi else '—'} "
           f"(TEFAS) | Son kontrol: {datetime.now():%d.%m.%Y %H:%M} | "
           "Gun sutunlari bu haftanin gunluk degisimleridir. Yatirim tavsiyesi degildir.")

def renk(v):
    if isinstance(v, (int, float)) and not pd.isna(v):
        return "color: #2e7d32; font-weight: 600" if v > 0 else \
               ("color: #c62828; font-weight: 600" if v < 0 else "")
    return ""

yuzde_kolonlari = ["Gunluk %"] + list(GUN_ADLARI.values())
st.dataframe(
    df.style
      .map(renk, subset=yuzde_kolonlari)
      .format({k: "{:+.2f}" for k in yuzde_kolonlari}, na_rep="—"),
    use_container_width=True, hide_index=True,
    height=40 * len(FONLAR) + 60,
)

# ----------------- HAFTALIK SEYIR GRAFIGI -----------------
grafik_df = df.set_index("Fon")[list(GUN_ADLARI.values())].T
grafik_df.index = [ad.replace(" %", "") for ad in grafik_df.index]
if grafik_df.notna().any().any():
    st.subheader("Bu haftanin gun gun seyri (%)")
    st.line_chart(grafik_df)

st.caption("Kaynak: TEFAS. Fiyatlar gun sonu aciklanir; hafta ici bir gun "
           "bos gorunuyorsa o gunun verisi henuz yayinlanmamistir.")
