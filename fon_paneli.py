"""
Fon Takip Paneli v4 — Sekmeli tam surum

Sekme 1: 6 fonun ozet tablosu (fiyat, gun gun getiri, yatirimci/tutar degisimi)
Sekme 2-7: Her fon icin ayri analiz sayfasi:
  - Hisse fonlari (TLY, THF, DOH): ozet kartlar + hisse tablosu + gunluk grafik
  - Para piyasasi fonlari (TP2, PRY, PNU): fiyat seyri + gunluk getiri grafigi

Kaynaklar: FonParam (resmi TEFAS verisinin acik aynasi) -> TEFAS -> fundturkey
Gun ici tahminler: sepet hisselerinin Yahoo verisinden (~15 dk gecikmeli)

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
MEVDUAT_BENZERI = ["TP2", "PRY", "PNU"]
# Veri kaynaginda risk gelmezse kullanilacak yedekler (KAP'tan dogrulanmali)
RISK_YEDEK = {"TLY": 7, "THF": 6, "DOH": 6, "TP2": 1, "PRY": 1, "PNU": 1}
FON_ACIKLAMA = {
    "TLY": "Tera Portfoy Birinci Serbest Fon",
    "THF": "Tera Portfoy Hisse Senedi Fonu",
    "DOH": "Tera Portfoy Dorduncu Hisse Senedi Serbest Fon",
    "TP2": "Tera Portfoy Para Piyasasi Fonu",
    "PRY": "Pusula Portfoy Para Piyasasi Fonu",
    "PNU": "Pusula Portfoy Ikinci Para Piyasasi Fonu",
}

st.set_page_config(page_title="Fon Takip", page_icon="📊", layout="wide")
st.sidebar.header("Ayarlar")
duraklat = st.sidebar.toggle("⏸ Yenilemeyi durdur (adet girerken ac)",
                             value=False)
aralik = st.sidebar.slider("Yenileme araligi (dakika)", 1, 30, 5)
if not duraklat:
    st_autorefresh(interval=aralik * 60 * 1000, key="oto_yenile")
else:
    st.sidebar.warning("Otomatik yenileme KAPALI — adetleri girip "
                       "kaydettikten sonra bu anahtari geri kapat.")

# --- Portfoyum: fon adetleri (Kaydet butonlu form; URL'e islenir) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Portfoyum (adet)")
with st.sidebar.form("portfoy_formu"):
    _girisler = {}
    for _kod in FONLAR:
        try:
            _vars = float(st.query_params.get(_kod, "0"))
        except (TypeError, ValueError):
            _vars = 0.0
        _girisler[_kod] = st.number_input(_kod, min_value=0.0, value=_vars,
                                          step=1.0, format="%.2f")
    _b1, _b2 = st.columns(2)
    _kaydet = _b1.form_submit_button("💾 Kaydet", use_container_width=True)
    _sifirla = _b2.form_submit_button("🗑 Sifirla", use_container_width=True)
if _sifirla:
    for _kod in FONLAR:
        if _kod in st.query_params:
            del st.query_params[_kod]
    _girisler = {k: 0.0 for k in FONLAR}
    st.sidebar.success("Adetler sifirlandi.")
elif _kaydet:
    for _kod, _v in _girisler.items():
        if _v > 0:
            st.query_params[_kod] = f"{_v:g}"
        elif _kod in st.query_params:
            del st.query_params[_kod]
ADETLER = {k: float(_girisler[k] or 0.0) for k in FONLAR}
with st.sidebar.expander("❓ Adet kismi nasil kullanilir?"):
    st.markdown(
        "**1.** Ustteki *Yenilemeyi durdur* anahtarini ac (sayfa sabitlenir).\n\n"
        "**2.** Her fonun kutusuna elindeki **pay adedini** yaz — aracinin/"
        "bankanin uygulamasinda 'adet' veya 'pay sayisi' olarak gorunur. "
        "Kusuratli girebilirsin (orn. 150,25). Elinde olmayan fonu 0 birak.\n\n"
        "**3.** **💾 Kaydet**'e bas: tabloda *Adet* ve *Benim Tutarim* "
        "sutunlari dolar, ustte toplam portfoy degerin cikar.\n\n"
        "**4.** Anahtari geri kapat, yenileme devam etsin.\n\n"
        "**Kalicilik:** Kaydedilen adetler sitenin adresine islenir — o "
        "adresi yer imine eklersen her aciliste otomatik gelir.\n\n"
        "**🗑 Sifirla:** tum adetleri ve adresteki kayitlari temizler.\n\n"
        "**Kutu calismazsa garantili yontem:** adresin sonuna elle yaz: "
        "`...streamlit.app/?TLY=150&THF=200`")

# ================= VERI KAYNAKLARI =================
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
    bitis = datetime.now()
    baslangic = bitis - timedelta(days=gun)
    r = requests.get(
        f"https://fonparam.apimapi.net/funds/{kod}/historical",
        params={"start_date": baslangic.strftime("%Y-%m-%d"),
                "end_date": bitis.strftime("%Y-%m-%d")},
        headers={"User-Agent": TARAYICI["User-Agent"]}, timeout=10)
    veri = r.json()
    if isinstance(veri, dict):
        veri = veri.get("data", [])
    if not veri:
        return None
    t = pd.DataFrame(veri).rename(columns={
        "date": "TARIH", "value": "FIYAT",
        "investor_count": "KISISAYISI", "aum": "PORTFOYBUYUKLUK",
        "risk_value": "RISK"})
    t["TARIH"] = pd.to_datetime(t["TARIH"])
    for k in ["FIYAT", "KISISAYISI", "PORTFOYBUYUKLUK", "RISK"]:
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
    t["RISK"] = None  # TEFAS bu uctan risk degeri dondurmez
    for k in ["FIYAT", "KISISAYISI", "PORTFOYBUYUKLUK"]:
        t[k] = pd.to_numeric(t[k], errors="coerce")
    t = t.sort_values("TARIH").reset_index(drop=True)
    t["Degisim"] = t["FIYAT"].pct_change() * 100
    return t

@st.cache_data(ttl=300, show_spinner=False)
def fon_gecmisi(kod, gun=45):
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

# ================= HISSE METRIKLERI (tum sepetler tek seferde) =================
TUM_HISSELER = tuple(sorted({h for sepet in SEPETLER.values() for h in sepet}))

@st.cache_data(ttl=300, show_spinner="Hisse verileri guncelleniyor...")
def hisse_metrikleri(hisseler):
    semboller = [f"{h}.IS" for h in hisseler]
    try:  # tek toplu indirme (35 ayri istek yerine 1)
        toplu = yf.download(semboller, period="3mo", interval="1d",
                            progress=False, auto_adjust=True,
                            group_by="ticker", threads=True)
    except Exception:
        toplu = None
    satirlar = []
    for h in hisseler:
        try:
            if toplu is not None and f"{h}.IS" in getattr(toplu.columns, "levels", [[]])[0]:
                k = toplu[f"{h}.IS"]["Close"].dropna()
            else:  # toplu indirme basarisizsa tek tek dene
                df = yf.download(f"{h}.IS", period="3mo", interval="1d",
                                 progress=False, auto_adjust=True)
                k = df["Close"].squeeze().dropna()
            if len(k) < 20:
                raise ValueError("yetersiz veri")
            son = float(k.iloc[-1])
            gun = (son / float(k.iloc[-2]) - 1) * 100
            hafta = (son / float(k.iloc[-6]) - 1) * 100 if len(k) > 6 else None
            ay = (son / float(k.iloc[-22]) - 1) * 100 if len(k) > 22 else None
            sma = (son / float(k.rolling(20).mean().iloc[-1]) - 1) * 100
            fark = k.diff()
            kazanc = fark.clip(lower=0).rolling(14).mean()
            kayip = (-fark.clip(upper=0)).rolling(14).mean()
            rsi = float((100 - 100 / (1 + kazanc / kayip)).iloc[-1])
            satirlar.append(dict(Hisse=h, Fiyat=son, Gun=gun, Hafta=hafta,
                                 Ay=ay, SMA20=sma, RSI=rsi, Taban=gun <= -9.5))
        except Exception:
            satirlar.append(dict(Hisse=h, Fiyat=None, Gun=None, Hafta=None,
                                 Ay=None, SMA20=None, RSI=None, Taban=False))
    return pd.DataFrame(satirlar)

METRIK = hisse_metrikleri(TUM_HISSELER)

def sinyal(r):
    if pd.isna(r["RSI"]):
        return "veri yok"
    if r["Taban"]:
        return "🔻 TABAN"
    if r["RSI"] > 70:
        return "asiri alim"
    if r["RSI"] < 30:
        return "asiri satim"
    if r["SMA20"] > 0 and (r["Hafta"] or 0) > 0:
        return "yukari trend"
    if r["SMA20"] < 0 and (r["Hafta"] or 0) < 0:
        return "asagi trend"
    return "notr"

def sepet_tahmini(kod):
    sepet = SEPETLER.get(kod)
    if not sepet:
        return None
    alt = METRIK[METRIK["Hisse"].isin(sepet)].dropna(subset=["Gun"])
    if alt.empty:
        return None
    agirliklar = alt["Hisse"].map(sepet)
    if agirliklar.sum() < 20:
        return None
    return float((alt["Gun"] * agirliklar / 100).sum())

# ================= BICIMLEYICILER =================
def tr_sayi(deger, ondalik=0):
    if deger is None or pd.isna(deger):
        return "—"
    s = f"{deger:,.{ondalik}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def yuzde_str(deger, tahmin=False):
    if deger is None or pd.isna(deger):
        return "—"
    return f"{'~' if tahmin else ''}{deger:+.2f}".replace(".", ",")

def tl_kisa(deger):
    if deger is None or pd.isna(deger):
        return "—"
    m = abs(deger)
    if m >= 1e9:
        s = f"{deger/1e9:+.2f} mlr"
    elif m >= 1e6:
        s = f"{deger/1e6:+.1f} mn"
    else:
        s = f"{deger/1e3:+.0f} bin"
    return s.replace(".", ",")

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

def isaret_renk(v):
    if isinstance(v, str) and v not in ("—", ""):
        if v.startswith("+"):
            return "color: #2e7d32; font-weight: 600"
        if v.startswith("-"):
            return "color: #c62828; font-weight: 600"
    return ""

def sayi_renk(v):
    if isinstance(v, (int, float)) and not pd.isna(v):
        if v > 0:
            return "color: #2e7d32; font-weight: 600"
        if v < 0:
            return "color: #c62828; font-weight: 600"
    return ""

# ================= FON OZET TABLOSU =================
bugun = datetime.now().date()
pazartesi = bugun - timedelta(days=bugun.weekday())
BOS_EK = {"Son Veri": "—", "Yatirimci": "—",
          "Yat. Δ (gun)": "—", "Yat. Δ (hafta)": "—", "Yat. Δ (ay)": "—",
          "Toplam Tutar (TL)": "—",
          "Tutar Δ (gun)": "—", "Tutar Δ (hafta)": "—", "Tutar Δ (ay)": "—"}
satirlar, kaynaklar, resmi_yok = [], set(), 0
PORTFOY_TOPLAM = []
FON_VERI = {}  # sekmelerde tekrar kullanmak icin

for kod in FONLAR:
    t, kaynak = fon_gecmisi(kod)
    FON_VERI[kod] = t
    tahmin = sepet_tahmini(kod)

    if t is None:
        resmi_yok += 1
        adet = ADETLER.get(kod, 0)
        satir = {"Fon": kod, "Fiyat (TL)": "—",
                 "Risk": f"{RISK_YEDEK[kod]}/7" if kod in RISK_YEDEK else "—",
                 "Adet": tr_sayi(adet, 2) if adet else "—",
                 "Benim Tutarim (TL)": "—",
                 "Gunluk %": yuzde_str(tahmin, tahmin=True)}
        for gun_no, ad in GUN_ADLARI.items():
            hedef = pazartesi + timedelta(days=gun_no)
            satir[ad] = yuzde_str(tahmin, True) if hedef == bugun else "—"
        satir.update(BOS_EK)
        satirlar.append(satir)
        continue

    kaynaklar.add(kaynak)
    son = t.iloc[-1]
    bugun_resmi_var = (son["TARIH"].date() == bugun)
    if tahmin is None and not bugun_resmi_var and kod in MEVDUAT_BENZERI:
        tahmin = float(son["Degisim"])

    satir = {"Fon": kod,
             "Fiyat (TL)": tr_sayi(son["FIYAT"], 4 if son["FIYAT"] < 10 else 2)}
    risk = son.get("RISK")
    if pd.notna(risk):
        satir["Risk"] = f"{int(risk)}/7"
    else:
        satir["Risk"] = f"{RISK_YEDEK[kod]}/7" if kod in RISK_YEDEK else "—"
    adet = ADETLER.get(kod, 0)
    if adet and pd.notna(son["FIYAT"]):
        benim = adet * float(son["FIYAT"])
        PORTFOY_TOPLAM.append(benim)
        satir["Adet"] = tr_sayi(adet, 2)
        satir["Benim Tutarim (TL)"] = tr_sayi(benim, 2)
    else:
        satir["Adet"] = tr_sayi(adet, 2) if adet else "—"
        satir["Benim Tutarim (TL)"] = "—"
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

    satir["Son Veri"] = son["TARIH"].strftime("%d.%m")
    satir["Yatirimci"] = tr_sayi(son["KISISAYISI"])

    def onceki_satir(is_gunu):
        """is_gunu kadar onceki kaydi dondurur (yoksa None)."""
        return t.iloc[-(is_gunu + 1)] if len(t) > is_gunu else None

    def delta(kolon, ref, bicim):
        if ref is None or pd.isna(son[kolon]) or pd.isna(ref[kolon]):
            return "—"
        return bicim(son[kolon] - ref[kolon])

    yat_bicim = lambda f: f"{int(f):+,}".replace(",", ".")
    dun, hafta_once, ay_once = onceki_satir(1), onceki_satir(5), onceki_satir(21)
    satir["Yat. Δ (gun)"] = delta("KISISAYISI", dun, yat_bicim)
    satir["Yat. Δ (hafta)"] = delta("KISISAYISI", hafta_once, yat_bicim)
    satir["Yat. Δ (ay)"] = delta("KISISAYISI", ay_once, yat_bicim)
    satir["Toplam Tutar (TL)"] = tr_sayi(son["PORTFOYBUYUKLUK"], 2)
    satir["Tutar Δ (gun)"] = delta("PORTFOYBUYUKLUK", dun, tl_kisa)
    satir["Tutar Δ (hafta)"] = delta("PORTFOYBUYUKLUK", hafta_once, tl_kisa)
    satir["Tutar Δ (ay)"] = delta("PORTFOYBUYUKLUK", ay_once, tl_kisa)
    satirlar.append(satir)

fon_df = pd.DataFrame(satirlar)

# ================= GORUNUM =================
st.title("📊 Fon Takip Paneli")
st.caption(f"Son kontrol: {datetime.now():%d.%m.%Y %H:%M} | ~ = gun ici tahmin "
           "(sepet hisselerinden, ~15 dk gecikmeli); resmi fiyat gun sonu "
           "kesinlesir. Yatirim tavsiyesi degildir.")
st.sidebar.caption("Resmi veri: "
                   + (", ".join(sorted(kaynaklar)) if kaynaklar else "ulasilamiyor")
                   + " | Tahmin/hisse: Yahoo Finance")

sekmeler = st.tabs(["📊 Genel"] + FONLAR)

# ---- Sekme 1: Genel tablo ----
with sekmeler[0]:
    if resmi_yok == len(FONLAR):
        st.error("Resmi fon verilerine su an ulasilamiyor; sadece ~ tahminler "
                 "gosteriliyor. Panel her yenilemede tekrar dener.")
    elif resmi_yok:
        st.warning(f"{resmi_yok} fonun resmi verisi alinamadi.")
    if PORTFOY_TOPLAM:
        st.metric("💼 Portfoyumun guncel degeri (son resmi fiyatlarla)",
                  tr_sayi(sum(PORTFOY_TOPLAM), 2) + " TL")
    yuzde_kolonlari = ["Gunluk %"] + list(GUN_ADLARI.values())
    degisim_kolonlari = ["Yat. Δ (gun)", "Yat. Δ (hafta)", "Yat. Δ (ay)",
                         "Tutar Δ (gun)", "Tutar Δ (hafta)", "Tutar Δ (ay)"]
    st.dataframe(fon_df.style
                   .map(renk, subset=yuzde_kolonlari)
                   .map(isaret_renk, subset=degisim_kolonlari),
                 use_container_width=True, hide_index=True,
                 height=40 * len(FONLAR) + 60)
    st.caption("Son Veri: resmi verinin ait oldugu tarih (fon fiyatlari gun "
               "sonunda aciklanir, saat yayinlanmaz). Δ bazlari: gun = onceki "
               "is gunu, hafta = 5 is gunu once, ay = 21 is gunu (~1 takvim "
               "ayi) once.")

# ---- Hisse fonu sekmesi ----
def hisse_fonu_sekmesi(kod):
    sepet = SEPETLER[kod]
    st.subheader(f"{kod} — {FON_ACIKLAMA.get(kod, '')}")
    st.caption(f"Sepet: son aylik KAP raporundaki {len(sepet)} hisse "
               f"(fonun ~%{sum(sepet.values()):.0f}'i). Her ay guncellenir.")

    alt = METRIK[METRIK["Hisse"].isin(sepet)].copy()
    alt["Agirlik"] = alt["Hisse"].map(sepet)
    alt["Sinyal"] = alt.apply(sinyal, axis=1)
    alt = alt.sort_values("Agirlik", ascending=False)
    gecerli = alt.dropna(subset=["Gun"])

    k1, k2, k3, k4 = st.columns(4)
    if not gecerli.empty:
        w = gecerli["Agirlik"]
        k1.metric("Sepet agirlikli gunluk perf.",
                  f"%{(gecerli['Gun']*w).sum()/w.sum():+.2f}")
        en_iyi = gecerli.loc[gecerli["Gun"].idxmax()]
        en_kotu = gecerli.loc[gecerli["Gun"].idxmin()]
        k2.metric(f"En iyi: {en_iyi['Hisse']}", f"%{en_iyi['Gun']:+.2f}")
        k3.metric(f"En kotu: {en_kotu['Hisse']}", f"%{en_kotu['Gun']:+.2f}")
        taban_sayi = int(gecerli["Taban"].sum())
        asiri = int((gecerli["RSI"] > 70).sum())
        k4.metric("Asiri alim / Taban", f"{asiri} / {taban_sayi}")
        if taban_sayi:
            st.warning("Taban bolgesinde hisse var: "
                       + ", ".join(gecerli[gecerli["Taban"]]["Hisse"]))

    goster = alt[["Hisse", "Agirlik", "Fiyat", "Gun", "Hafta", "Ay",
                  "SMA20", "RSI", "Sinyal"]].rename(columns={
        "Agirlik": "Agirlik %", "Fiyat": "Fiyat (TL)", "Gun": "Gun %",
        "Hafta": "Hafta %", "Ay": "Ay %", "SMA20": "SMA20 Fark %"})
    st.dataframe(goster.style
                   .map(sayi_renk, subset=["Gun %", "Hafta %", "Ay %", "SMA20 Fark %"])
                   .format({"Fiyat (TL)": "{:.2f}", "Gun %": "{:+.2f}",
                            "Hafta %": "{:+.2f}", "Ay %": "{:+.2f}",
                            "SMA20 Fark %": "{:+.2f}", "RSI": "{:.1f}",
                            "Agirlik %": "{:.1f}"}, na_rep="—"),
                 use_container_width=True, hide_index=True,
                 height=38 * len(alt) + 60)

    if not gecerli.empty:
        st.markdown("**Gunluk degisim (%)**")
        st.bar_chart(gecerli.set_index("Hisse")["Gun"])

# ---- Para piyasasi fonu sekmesi ----
def para_fonu_sekmesi(kod):
    st.subheader(f"{kod} — {FON_ACIKLAMA.get(kod, '')}")
    st.info("Bu bir para piyasasi fonudur: portfoyunde hisse senedi degil "
            "mevduat, repo ve kisa vadeli borclanma araclari bulunur. Bu "
            "yuzden hisse analizi yerine fonun kendi seyri gosterilir.")
    t = FON_VERI.get(kod)
    if t is None or len(t) < 3:
        st.warning("Resmi veri su an alinamiyor.")
        return
    son = t.iloc[-1]
    yillik = float(son["Degisim"]) * 252 if pd.notna(son["Degisim"]) else None
    k1, k2, k3 = st.columns(3)
    k1.metric("Son fiyat (TL)", tr_sayi(son["FIYAT"], 4))
    k2.metric("Son gunluk getiri", "%" + yuzde_str(float(son["Degisim"])))
    k3.metric("Kabaca yillik esdegeri",
              f"~%{yillik:.0f}" if yillik is not None else "—")
    st.markdown("**Fiyat seyri (son 30 gun)**")
    st.line_chart(t.set_index("TARIH")["FIYAT"])
    st.markdown("**Gunluk getiri (%)**")
    st.bar_chart(t.dropna(subset=["Degisim"]).set_index("TARIH")["Degisim"])

for i, kod in enumerate(FONLAR, start=1):
    with sekmeler[i]:
        if kod in SEPETLER:
            hisse_fonu_sekmesi(kod)
        else:
            para_fonu_sekmesi(kod)
