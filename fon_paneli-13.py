"""
Fon Takip Paneli v5
- Hucre bosluklari kapatildi: resmi veri gelmeyen gunler sepet tahminiyle (~) dolar
- Gunluk %'nin yanina Haftalik % kolonu eklendi
- Genel sekmesine "Gunun Hareket Analizi" (otomatik yazili yorum) eklendi
- Fon sekmelerine hisse yorum kutusu + teknik durum rehberi eklendi
- Bedelsiz/bolunme kaynakli sahte "%-19" hareketleri ayirt edilir
- Gorunum: kartlar, rozetler, renkli sinyaller

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
RISK_YEDEK = {"TLY": 7, "THF": 6, "DOH": 6, "TP2": 1, "PRY": 1, "PNU": 1}
# (alim valoru, satim valoru) — is gunu. TLY tefasfon'dan dogrulandi;
# digerleri fon turune gore genel kural, izahnameden teyit edin.
VALOR = {"TLY": (1, 2), "THF": (1, 2), "DOH": (1, 2),
         "TP2": (0, 0), "PRY": (0, 0), "PNU": (0, 0)}
KESME_SAATI = (13, 30)  # TEFAS standart kesme: 13:30

def simdi_tr():
    """Sunucu UTC calisir; Turkiye saati = UTC+3."""
    return datetime.utcnow() + timedelta(hours=3)
FON_ACIKLAMA = {
    "TLY": "Tera Portfoy Birinci Serbest Fon",
    "THF": "Tera Portfoy Hisse Senedi Fonu",
    "DOH": "Tera Portfoy Dorduncu Hisse Senedi Serbest Fon",
    "TP2": "Tera Portfoy Para Piyasasi Fonu",
    "PRY": "Pusula Portfoy Para Piyasasi Fonu",
    "PNU": "Pusula Portfoy Ikinci Para Piyasasi Fonu",
}

st.set_page_config(page_title="Fon Takip", page_icon="📊", layout="wide")

# ---------- Gorunum: CSS ----------
st.markdown("""
<style>
.block-container {padding-top: 1.2rem;}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #eaf1fb 0%, #f3f7fd 100%);
  border-right: 3px solid #1f4e79;
}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: #1f4e79; border-left: 4px solid #1f4e79;
  padding-left: 8px; border-radius: 2px;
}
[data-testid="stSidebar"] [data-testid="stForm"] {
  background: #ffffff; border: 1px solid #d5e0f0; border-radius: 12px;
  padding: 10px; box-shadow: 0 1px 3px rgba(16,24,40,.08);
}
[data-testid="stMetric"] {
  background: #f7f9fc; border: 1px solid #e3e9f2; border-radius: 14px;
  padding: 12px 16px; box-shadow: 0 1px 3px rgba(16,24,40,.06);
}
[data-testid="stMetricLabel"] {color: #5b6b85; font-size: 0.85rem;}
h1 {letter-spacing: -0.5px;}
div[data-baseweb="tab-list"] {gap: 4px;}
button[data-baseweb="tab"] {
  background: #f2f5fa; border-radius: 10px 10px 0 0; padding: 6px 14px;
}
button[data-baseweb="tab"][aria-selected="true"] {
  background: #1f4e79; color: white;
}
.analiz-kutu {
  background: #f7f9fc; border: 1px solid #e3e9f2; border-left: 4px solid #1f4e79;
  border-radius: 10px; padding: 14px 18px; margin: 6px 0; line-height: 1.55;
}
.tuyo-kutu {
  background: #fffdf5; border: 1px solid #f0e6c8; border-left: 4px solid #d9a441;
  border-radius: 10px; padding: 14px 18px; margin: 6px 0; line-height: 1.55;
}
/* Kenar cubugu ac/kapa dugmesini belirginlestir */
[data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {
  background: #1f4e79 !important; border-radius: 12px !important;
  padding: 8px 14px 8px 10px !important;
  box-shadow: 0 2px 8px rgba(31,78,121,.4) !important;
}
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="collapsedControl"] svg {
  stroke: #ffffff !important; color: #ffffff !important;
}
[data-testid="stSidebarCollapsedControl"]::after,
[data-testid="collapsedControl"]::after {
  content: "⚙ Ayarlar"; color: #ffffff; font-weight: 700;
  font-size: 0.95rem; margin-left: 6px;
}
</style>""", unsafe_allow_html=True)

st.sidebar.header("Ayarlar")
duraklat = st.sidebar.toggle("⏸ Yenilemeyi durdur (adet girerken ac)",
                             value=False)
aralik = st.sidebar.slider("Yenileme araligi (dakika)", 1, 30, 5)
if not duraklat:
    st_autorefresh(interval=aralik * 60 * 1000, key="oto_yenile")
else:
    st.sidebar.warning("Otomatik yenileme KAPALI — isin bitince anahtari kapat.")

# ---------- Portfoyum ----------
st.sidebar.markdown("---")
st.sidebar.subheader("Portfoyum")
with st.sidebar.form("portfoy_formu"):
    st.caption("Sol: adet | Sag: ort. alis fiyati (TL)")
    _girisler, _maliyet_girisler = {}, {}
    for _kod in FONLAR:
        try:
            _vars = float(st.query_params.get(_kod, "0"))
        except (TypeError, ValueError):
            _vars = 0.0
        try:
            _mvars = float(st.query_params.get(f"{_kod}m", "0"))
        except (TypeError, ValueError):
            _mvars = 0.0
        _c1, _c2 = st.columns(2)
        _girisler[_kod] = _c1.number_input(f"{_kod} adet", min_value=0.0,
                                           value=_vars, step=1.0,
                                           format="%.2f")
        _maliyet_girisler[_kod] = _c2.number_input(f"{_kod} alis", min_value=0.0,
                                                   value=_mvars, step=0.1,
                                                   format="%.4f")
    _b1, _b2 = st.columns(2)
    _kaydet = _b1.form_submit_button("💾 Kaydet", use_container_width=True)
    _sifirla = _b2.form_submit_button("🗑 Sifirla", use_container_width=True)
if _sifirla:
    for _kod in FONLAR:
        for _anahtar in (_kod, f"{_kod}m"):
            if _anahtar in st.query_params:
                del st.query_params[_anahtar]
    _girisler = {k: 0.0 for k in FONLAR}
    _maliyet_girisler = {k: 0.0 for k in FONLAR}
    st.sidebar.success("Portfoy bilgileri sifirlandi.")
elif _kaydet:
    for _kod in FONLAR:
        for _anahtar, _v in ((_kod, _girisler[_kod]),
                             (f"{_kod}m", _maliyet_girisler[_kod])):
            if _v > 0:
                st.query_params[_anahtar] = f"{_v:g}"
            elif _anahtar in st.query_params:
                del st.query_params[_anahtar]
ADETLER = {k: float(_girisler[k] or 0.0) for k in FONLAR}
MALIYETLER = {k: float(_maliyet_girisler[k] or 0.0) for k in FONLAR}
with st.sidebar.expander("❓ Portfoyum nasil kullanilir?"):
    st.markdown(
        "**1.** Ustteki *Yenilemeyi durdur* anahtarini ac.\n\n"
        "**2.** Her fon icin **adet** (aracinin uygulamasindaki pay sayisi) "
        "ve **ortalama alis fiyatini** yaz. Alis fiyatin araci kurum "
        "uygulamasinda 'ortalama maliyet' olarak gorunur. Elinde olmayani "
        "0 birak; sadece adet girersen K/Z hesaplanmaz ama guncel tutar "
        "gorunur.\n\n"
        "**3.** **💾 Kaydet**'e bas — tabloda Adet, Tutar, Maliyet ve K/Z "
        "dolar; ustte toplam kar/zararin cikar.\n\n"
        "**4.** Anahtari geri kapat.\n\n"
        "**Kalicilik:** girilenler adrese islenir; sayfayi yer imine ekle.\n\n"
        "**🗑 Sifirla:** tum adet ve maliyetleri temizler.\n\n"
        "**Garantili yontem:** adresin sonuna `?TLY=150&TLYm=5000` yaz "
        "(adet icin fon kodu, alis fiyati icin kodun sonuna 'm').")

# ---------- Veri kaynaklari ----------
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
    t["RISK"] = None
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

# ---------- Hisse verileri (toplu) ----------
TUM_HISSELER = tuple(sorted({h for sepet in SEPETLER.values() for h in sepet}))

@st.cache_data(ttl=300, show_spinner="Hisse verileri guncelleniyor...")
def hisse_verileri(hisseler):
    """(METRIK, DEG) dondurur. DEG: tarih x hisse gunluk % degisim tablosu."""
    semboller = [f"{h}.IS" for h in hisseler]
    try:
        toplu = yf.download(semboller, period="3mo", interval="1d",
                            progress=False, auto_adjust=True,
                            group_by="ticker", threads=True)
    except Exception:
        toplu = None
    metrik_satirlar, deg_seriler = [], {}
    for h in hisseler:
        try:
            if toplu is not None and f"{h}.IS" in getattr(toplu.columns, "levels", [[]])[0]:
                k = toplu[f"{h}.IS"]["Close"].dropna()
            else:
                df = yf.download(f"{h}.IS", period="3mo", interval="1d",
                                 progress=False, auto_adjust=True)
                k = df["Close"].squeeze().dropna()
            if len(k) < 20:
                raise ValueError("yetersiz veri")
            deg_seriler[h] = k.pct_change() * 100
            son = float(k.iloc[-1])
            gun = float(deg_seriler[h].iloc[-1])
            hafta = (son / float(k.iloc[-6]) - 1) * 100 if len(k) > 6 else None
            ay = (son / float(k.iloc[-22]) - 1) * 100 if len(k) > 22 else None
            sma = (son / float(k.rolling(20).mean().iloc[-1]) - 1) * 100
            fark = k.diff()
            kazanc = fark.clip(lower=0).rolling(14).mean()
            kayip = (-fark.clip(upper=0)).rolling(14).mean()
            rsi = float((100 - 100 / (1 + kazanc / kayip)).iloc[-1])
            metrik_satirlar.append(dict(Hisse=h, Fiyat=son, Gun=gun,
                                        Hafta=hafta, Ay=ay, SMA20=sma,
                                        RSI=rsi))
        except Exception:
            metrik_satirlar.append(dict(Hisse=h, Fiyat=None, Gun=None,
                                        Hafta=None, Ay=None, SMA20=None,
                                        RSI=None))
    METRIK = pd.DataFrame(metrik_satirlar)
    DEG = pd.DataFrame(deg_seriler)
    if not DEG.empty:
        DEG.index = pd.to_datetime(DEG.index).date
    return METRIK, DEG

METRIK, DEG = hisse_verileri(TUM_HISSELER)

def hareket_turu(chg):
    """Gunluk degisimi siniflar. BIST limiti ~%10 oldugundan onu asan
    hareketler genelde bedelsiz/bolunme fiyat ayarlamasidir."""
    if chg is None or pd.isna(chg):
        return "veri yok"
    if chg <= -10.5 or chg >= 10.5:
        return "ayarlama?"
    if chg <= -9.5:
        return "taban"
    if chg >= 9.5:
        return "tavan"
    return "normal"

def seri_say(h, yon):
    """Hissenin sonda kac gun ust uste sert (+/-%9.5+) gittigini sayar."""
    if h not in DEG.columns:
        return 0
    s = DEG[h].dropna()
    sayac = 0
    for chg in reversed(s.tolist()):
        if (yon == "-" and chg <= -9.5) or (yon == "+" and chg >= 9.5):
            sayac += 1
        else:
            break
    return sayac

def sinyal(r):
    tur = hareket_turu(r["Gun"])
    if pd.isna(r["RSI"]):
        return "veri yok"
    if tur == "ayarlama?":
        return "⚙ fiyat ayarlamasi?"
    if tur == "taban":
        return "🔻 TABAN"
    if tur == "tavan":
        return "🔺 TAVAN"
    if r["RSI"] > 70:
        return "asiri alim"
    if r["RSI"] < 30:
        return "asiri satim"
    if r["SMA20"] > 0 and (r["Hafta"] or 0) > 0:
        return "yukari trend"
    if r["SMA20"] < 0 and (r["Hafta"] or 0) < 0:
        return "asagi trend"
    return "notr"

def sepet_tahmini_tarih(kod, tarih=None):
    """Belirli bir gun icin sepet tahmini; tarih None ise son gun."""
    sepet = SEPETLER.get(kod)
    if not sepet or DEG.empty:
        return None
    if tarih is None:
        satir = DEG.iloc[-1]
    elif tarih in DEG.index:
        satir = DEG.loc[tarih]
    else:
        return None
    toplam, kapsanan = 0.0, 0.0
    for h, w in sepet.items():
        if h in satir.index and pd.notna(satir[h]):
            toplam += w / 100 * float(satir[h])
            kapsanan += w
    return toplam if kapsanan >= 20 else None

# ---------- Bicimleyiciler ----------
def tr_sayi(d, o=0):
    if d is None or pd.isna(d):
        return "—"
    return f"{d:,.{o}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def yuzde_str(d, tahmin=False):
    if d is None or pd.isna(d):
        return "—"
    return f"{'~' if tahmin else ''}{d:+.2f}".replace(".", ",")

def tl_kisa(d):
    if d is None or pd.isna(d):
        return "—"
    m = abs(d)
    if m >= 1e9:
        s = f"{d/1e9:+.2f} mlr"
    elif m >= 1e6:
        s = f"{d/1e6:+.1f} mn"
    else:
        s = f"{d/1e3:+.0f} bin"
    return s.replace(".", ",")

def renk(v):
    if isinstance(v, str) and v not in ("—", ""):
        try:
            s = float(v.replace("~", "").replace(",", "."))
            stil = "font-style: italic; " if v.startswith("~") else ""
            if s > 0:
                return stil + "color: #2e7d32; font-weight: 600"
            if s < 0:
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

def risk_renk(v):
    if isinstance(v, str) and "/" in v:
        try:
            r = int(v.split("/")[0])
            if r >= 6:
                return "background-color: #fdecea; color: #c62828; font-weight: 700"
            if r >= 3:
                return "background-color: #fff8e1; color: #9c6f00; font-weight: 700"
            return "background-color: #e8f5e9; color: #2e7d32; font-weight: 700"
        except ValueError:
            pass
    return ""

def sinyal_renk(v):
    stiller = {
        "🔻 TABAN": "background-color: #fdecea; color: #b71c1c; font-weight: 700",
        "🔺 TAVAN": "background-color: #e8f5e9; color: #1b5e20; font-weight: 700",
        "⚙ fiyat ayarlamasi?": "background-color: #ede7f6; color: #4527a0",
        "asiri alim": "background-color: #fff3e0; color: #e65100",
        "asiri satim": "background-color: #e3f2fd; color: #0d47a1",
        "yukari trend": "color: #2e7d32; font-weight: 600",
        "asagi trend": "color: #c62828; font-weight: 600",
    }
    return stiller.get(v, "")

# ---------- Fon tablosu ----------
bugun = simdi_tr().date()
pazartesi = bugun - timedelta(days=bugun.weekday())
satirlar, kaynaklar, resmi_yok = [], set(), 0
PORTFOY_TOPLAM, PORTFOY_MALIYET, FON_VERI, FON_ANALIZ = [], [], {}, {}

for kod in FONLAR:
    t, kaynak = fon_gecmisi(kod)
    FON_VERI[kod] = t
    tahmin_bugun = sepet_tahmini_tarih(kod)

    adet = ADETLER.get(kod, 0)
    if t is None:
        resmi_yok += 1
        satir = {"Fon": kod, "Fiyat (TL)": "—",
                 "Risk": f"{RISK_YEDEK[kod]}/7" if kod in RISK_YEDEK else "—",
                 "Adet": tr_sayi(adet, 2) if adet else "—",
                 "Benim Tutarim (TL)": "—",
                 "Maliyetim (TL)": "—", "K/Z (TL)": "—", "K/Z %": "—",
                 "Gunluk %": yuzde_str(tahmin_bugun, tahmin=True),
                 "Haftalik %": "—"}
        for gun_no, ad in GUN_ADLARI.items():
            hedef = pazartesi + timedelta(days=gun_no)
            th = sepet_tahmini_tarih(kod, hedef)
            satir[ad] = yuzde_str(th, True) if th is not None else "—"
        satir.update({"Son Veri": "—", "Yatirimci": "—",
                      "Yat. Δ (gun)": "—", "Yat. Δ (hafta)": "—",
                      "Yat. Δ (ay)": "—", "Toplam Tutar (TL)": "—",
                      "Tutar Δ (gun)": "—", "Tutar Δ (hafta)": "—",
                      "Tutar Δ (ay)": "—"})
        satirlar.append(satir)
        continue

    kaynaklar.add(kaynak)
    son = t.iloc[-1]
    son_resmi_tarih = son["TARIH"].date()
    bugun_resmi_var = (son_resmi_tarih == bugun)
    if tahmin_bugun is None and not bugun_resmi_var and kod in MEVDUAT_BENZERI:
        tahmin_bugun = float(son["Degisim"])

    satir = {"Fon": kod,
             "Fiyat (TL)": tr_sayi(son["FIYAT"], 4 if son["FIYAT"] < 10 else 2)}
    risk = son.get("RISK")
    satir["Risk"] = (f"{int(risk)}/7" if pd.notna(risk)
                     else (f"{RISK_YEDEK[kod]}/7" if kod in RISK_YEDEK else "—"))
    if adet and pd.notna(son["FIYAT"]):
        benim = adet * float(son["FIYAT"])
        PORTFOY_TOPLAM.append(benim)
        satir["Adet"] = tr_sayi(adet, 2)
        satir["Benim Tutarim (TL)"] = tr_sayi(benim, 2)
        alis = MALIYETLER.get(kod, 0)
        if alis > 0:
            maliyet = adet * alis
            PORTFOY_MALIYET.append(maliyet)
            kz = benim - maliyet
            satir["Maliyetim (TL)"] = tr_sayi(maliyet, 2)
            satir["K/Z (TL)"] = tl_kisa(kz)
            satir["K/Z %"] = yuzde_str((benim / maliyet - 1) * 100)
        else:
            satir["Maliyetim (TL)"] = "—"
            satir["K/Z (TL)"] = "—"
            satir["K/Z %"] = "—"
    else:
        satir["Adet"] = tr_sayi(adet, 2) if adet else "—"
        satir["Benim Tutarim (TL)"] = "—"
        satir["Maliyetim (TL)"] = "—"
        satir["K/Z (TL)"] = "—"
        satir["K/Z %"] = "—"

    # Gunluk %
    if bugun_resmi_var:
        gunluk_v, gunluk_t = float(son["Degisim"]), False
    elif tahmin_bugun is not None:
        gunluk_v, gunluk_t = tahmin_bugun, True
    else:
        gunluk_v, gunluk_t = float(son["Degisim"]), False
    satir["Gunluk %"] = yuzde_str(gunluk_v, gunluk_t)

    # Haftalik %: resmi 5 is gunu; bugunun resmi verisi yoksa tahmini zincirle
    if len(t) > 5 and pd.notna(t["FIYAT"].iloc[-6]):
        hafta_resmi = (float(son["FIYAT"]) / float(t["FIYAT"].iloc[-6]) - 1) * 100
        if not bugun_resmi_var and tahmin_bugun is not None:
            hafta_v = ((1 + hafta_resmi / 100) * (1 + tahmin_bugun / 100) - 1) * 100
            satir["Haftalik %"] = yuzde_str(hafta_v, tahmin=True)
        else:
            satir["Haftalik %"] = yuzde_str(hafta_resmi)
    else:
        satir["Haftalik %"] = "—"

    # Hafta ici gunler: resmi -> yoksa o gunun sepet tahmini -> para fonu tasima
    resmi_gunler = {r["TARIH"].date(): float(r["Degisim"])
                    for _, r in t.iterrows() if pd.notna(r["Degisim"])}
    for gun_no, ad in GUN_ADLARI.items():
        hedef = pazartesi + timedelta(days=gun_no)
        if hedef in resmi_gunler:
            satir[ad] = yuzde_str(resmi_gunler[hedef])
        else:
            th = sepet_tahmini_tarih(kod, hedef)
            if th is None and kod in MEVDUAT_BENZERI and hedef <= bugun and hedef > son_resmi_tarih:
                th = float(son["Degisim"])
            satir[ad] = yuzde_str(th, True) if th is not None else "—"

    satir["Son Veri"] = son["TARIH"].strftime("%d.%m")
    satir["Yatirimci"] = tr_sayi(son["KISISAYISI"])

    def onceki_satir(g):
        return t.iloc[-(g + 1)] if len(t) > g else None

    def delta(kolon, ref, bicim):
        if ref is None or pd.isna(son[kolon]) or pd.isna(ref[kolon]):
            return "—"
        return bicim(son[kolon] - ref[kolon])

    yb = lambda f: f"{int(f):+,}".replace(",", ".")
    dun, hf, ayo = onceki_satir(1), onceki_satir(5), onceki_satir(21)
    satir["Yat. Δ (gun)"] = delta("KISISAYISI", dun, yb)
    satir["Yat. Δ (hafta)"] = delta("KISISAYISI", hf, yb)
    satir["Yat. Δ (ay)"] = delta("KISISAYISI", ayo, yb)
    satir["Toplam Tutar (TL)"] = tr_sayi(son["PORTFOYBUYUKLUK"], 2)
    satir["Tutar Δ (gun)"] = delta("PORTFOYBUYUKLUK", dun, tl_kisa)
    satir["Tutar Δ (hafta)"] = delta("PORTFOYBUYUKLUK", hf, tl_kisa)
    satir["Tutar Δ (ay)"] = delta("PORTFOYBUYUKLUK", ayo, tl_kisa)
    satirlar.append(satir)

    # Gunun hareket analizi icin veriyi sakla
    FON_ANALIZ[kod] = dict(gunluk=gunluk_v, tahmin=gunluk_t)

fon_df = pd.DataFrame(satirlar)

# ---------- Analiz yazilari ----------
def fon_gun_analizi(kod):
    """Gunun hareketini sepet katkilariyla aciklayan otomatik yorum."""
    bilgi = FON_ANALIZ.get(kod)
    if bilgi is None or bilgi["gunluk"] is None:
        return None
    v = bilgi["gunluk"]
    if kod in MEVDUAT_BENZERI:
        return (f"**{kod}** %{v:+.2f}: para piyasasi fonu — getirisi mevduat/"
                "repo faizinden gelir, gunluk oran duzenli seyreder; sert "
                "sapma gorursen veri hatasi olabilir.")
    sepet = SEPETLER.get(kod, {})
    alt = METRIK[METRIK["Hisse"].isin(sepet)].dropna(subset=["Gun"]).copy()
    if alt.empty:
        return None
    alt["Katki"] = alt.apply(lambda r: sepet[r["Hisse"]] / 100 * r["Gun"], axis=1)
    alt = alt.sort_values("Katki")
    dusuren = alt.head(2)
    yukselten = alt.tail(2).iloc[::-1]
    parcalar = [f"**{kod}** gunu {'~' if bilgi['tahmin'] else ''}%{v:+.2f} ile "
                f"{'yukselisle' if v > 0 else 'dususle' if v < 0 else 'yatay'} gecirdi."]
    neg = [f"{r['Hisse']} (%{r['Gun']:+.1f}, katki {r['Katki']:+.2f} puan)"
           for _, r in dusuren.iterrows() if r["Katki"] < -0.05]
    poz = [f"{r['Hisse']} (%{r['Gun']:+.1f}, katki {r['Katki']:+.2f} puan)"
           for _, r in yukselten.iterrows() if r["Katki"] > 0.05]
    if v >= 0:
        if poz:
            parcalar.append("Yukselisi en cok " + " ve ".join(poz) + " tasidi.")
        if neg:
            parcalar.append("Frenleyen taraf: " + " ve ".join(neg) + ".")
    else:
        if neg:
            parcalar.append("Dususun ana kaynagi " + " ve ".join(neg) + ".")
        if poz:
            parcalar.append("Kismen dengeleyen: " + " ve ".join(poz) + ".")
    ayar = [h for h in sepet if hareket_turu(
        float(METRIK.loc[METRIK["Hisse"] == h, "Gun"].iloc[0]))
        == "ayarlama?" if not METRIK.loc[METRIK["Hisse"] == h, "Gun"].isna().all()]
    if ayar:
        parcalar.append("Not: " + ", ".join(ayar) + " icin gorunen buyuk "
                        "hareket %10 BIST limitini astigi icin buyuk olasilikla "
                        "bedelsiz/bolunme fiyat ayarlamasidir, gercek kayip/"
                        "kazanc olmayabilir (KAP'tan teyit edin).")
    return " ".join(parcalar)

def hisse_yorumlari(kod):
    """Fon sekmesi icin dikkat ceken hisselerin yazili yorumu."""
    sepet = SEPETLER.get(kod, {})
    alt = METRIK[METRIK["Hisse"].isin(sepet)].dropna(subset=["Gun"])
    yorumlar = []
    for _, r in alt.iterrows():
        h, tur = r["Hisse"], hareket_turu(r["Gun"])
        if tur == "ayarlama?":
            yorumlar.append(f"**{h}** (%{r['Gun']:+.1f}): hareket BIST'in "
                            "±%10 limitini asiyor — buyuk olasilikla bedelsiz/"
                            "bolunme fiyat ayarlamasi veya veri duzeltmesi; "
                            "gercek dusus/yukselis sanma, KAP'tan kontrol et.")
        elif tur == "taban":
            s = seri_say(h, "-")
            ek = f" Ust uste {s}. sert dusus gunu." if s > 1 else ""
            yorumlar.append(f"**{h}** (%{r['Gun']:+.1f}): taban bolgesinde — "
                            f"alici cekilmis, satis baskisi hakim.{ek} Sig "
                            "hisselerde taban serileri genelde fon/buyuk "
                            "yatirimci cikisi kaynaklidir; likidite kuruyunca "
                            "satmak isteyen siraya girer.")
        elif tur == "tavan":
            s = seri_say(h, "+")
            ek = f" Ust uste {s}. sert yukselis gunu." if s > 1 else ""
            yorumlar.append(f"**{h}** (%{r['Gun']:+.1f}): tavan bolgesinde — "
                            f"talep arzi asmis.{ek} Genelde guclu para girisi "
                            "veya haber akisiyla olur; tavan acilirsa sert kar "
                            "satisi gelebilir.")
        elif pd.notna(r["RSI"]) and r["RSI"] > 85:
            yorumlar.append(f"**{h}** (RSI {r['RSI']:.0f}): asiri alimin da "
                            f"otesinde isinmis; aylik getiri %{(r['Ay'] or 0):+.0f}. "
                            "Bu bolgelerde duzeltmeler sert olabilir.")
        elif pd.notna(r["RSI"]) and r["RSI"] < 20:
            yorumlar.append(f"**{h}** (RSI {r['RSI']:.0f}): asiri satimin "
                            "dibinde; teknik tepki potansiyeli olusur ama "
                            "dusen trendde erken alim 'dusen bicak' riskidir.")
    if not yorumlar:
        yorumlar.append("Bugun sepette taban/tavan veya asiri uc RSI yok — "
                        "gorece sakin bir gun.")
    yorumlar.append("*Bu yorumlar fiyat verisinden otomatik uretilir; haber/"
                    "KAP bilgisi icermez ve yatirim tavsiyesi degildir.*")
    return yorumlar

TUYOLAR_FON = (
    "**Valor:** TLY'de alim T+1, satim T+2 — dusus basladiginda 'hemen cikis' "
    "yoktur, karar gecikmeli fiyattan gerceklesir; pozisyon boyutunu buna gore tut. "
    "**Akis takibi:** Yat. Δ ve Tutar Δ sutunlari gun/hafta/ay uclusunde birlikte "
    "eksiye donduyse fonun para girisiyle donen carki ters isliyor demektir — en "
    "erken uyari budur. **Risk 7/7 fonlar:** toplam birikimin ancak kaybetmeyi "
    "goze aldigin kismiyla tasinmalidir. **Ay basi:** portfoy raporlari yenilenir; "
    "sepetleri guncellemeden tahminlere korkorune guvenme.")

TUYOLAR_HISSE = (
    "**Asiri alim (RSI>70):** yukselis suruyor olabilir ama geri cekilme "
    "olasiligi artar — yeni alim icin genelde 'bekle-gor' bolgesi sayilir. "
    "**Asiri satim (RSI<30):** teknik tepki gelebilir; ancak dusen trendde erken "
    "alim 'dusen bicak' riskidir, donus sinyali beklemek daha guvenlidir. "
    "**Taban serisi:** likidite kurur; cikmak isteyen ancak acilis "
    "eslesmelerinde sirayla cikabilir — sig hisselerde bu gunlerce surebilir. "
    "**SMA20'den asiri uzaklasma (>%15):** lastik gibi gerilme; ortalamaya donus "
    "duzeltmeleri sik gorulur. **Tavan kovalamak:** tavandan alim FOMO'nun en "
    "pahali halidir; acilan tavanlarda sert kar satisi gelebilir.")

# ---------- Gorunum ----------
st.title("📊 Fon Takip Paneli")
st.caption(f"Son kontrol: {simdi_tr():%d.%m.%Y %H:%M} (TR) | ~ = tahmin (sepet "
           "hisselerinden); resmi fiyat gun sonu kesinlesir ve ~ kalkar. "
           "Yatirim tavsiyesi degildir.")
st.sidebar.caption("Resmi veri: "
                   + (", ".join(sorted(kaynaklar)) if kaynaklar else "ulasilamiyor")
                   + " | Tahmin/hisse: Yahoo Finance")

sekmeler = st.tabs(["📊 Genel"] + FONLAR)

with sekmeler[0]:
    if resmi_yok == len(FONLAR):
        st.error("Resmi fon verilerine ulasilamiyor; ~ tahminler gosteriliyor.")
    elif resmi_yok:
        st.warning(f"{resmi_yok} fonun resmi verisi alinamadi.")
    if PORTFOY_TOPLAM:
        deger = sum(PORTFOY_TOPLAM)
        if PORTFOY_MALIYET:
            maliyet = sum(PORTFOY_MALIYET)
            kz = deger - maliyet
            m1, m2, m3 = st.columns(3)
            m1.metric("💼 Portfoy degeri", tr_sayi(deger, 2) + " TL")
            m2.metric("🧾 Toplam maliyet", tr_sayi(maliyet, 2) + " TL")
            m3.metric("📈 Kar/Zarar", tl_kisa(kz) + " TL",
                      delta=f"%{(deger/maliyet-1)*100:+.2f}")
        else:
            st.metric("💼 Portfoy degeri (son resmi fiyatlarla)",
                      tr_sayi(deger, 2) + " TL")

    yuzde_kolonlari = ["Gunluk %", "Haftalik %", "K/Z %"] + list(GUN_ADLARI.values())
    degisim_kolonlari = ["Yat. Δ (gun)", "Yat. Δ (hafta)", "Yat. Δ (ay)",
                         "Tutar Δ (gun)", "Tutar Δ (hafta)", "Tutar Δ (ay)",
                         "K/Z (TL)"]
    st.dataframe(fon_df.style
                   .map(renk, subset=yuzde_kolonlari)
                   .map(isaret_renk, subset=degisim_kolonlari)
                   .map(risk_renk, subset=["Risk"]),
                 use_container_width=True, hide_index=True,
                 height=40 * len(FONLAR) + 60)
    st.caption("Risk: TEFAS 1-7 skalasi (7 = en yuksek). Δ bazlari: gun = "
               "onceki is gunu, hafta = 5 is gunu, ay = 21 is gunu. Bos gun "
               "kalmamasi icin resmi verisi henuz aciklanmamis gunler ~ "
               "tahminle doldurulur, resmi veri gelince kesinlesir.")

    st.subheader("📈 Fonlarin Karsilastirmali Seyri (45 gun, baslangic = 100)")
    karsilastirma = {}
    for kod in FONLAR:
        t = FON_VERI.get(kod)
        if t is not None and len(t) > 2 and pd.notna(t["FIYAT"].iloc[0]):
            karsilastirma[kod] = (t.set_index("TARIH")["FIYAT"]
                                  / float(t["FIYAT"].iloc[0]) * 100)
    if karsilastirma:
        st.line_chart(pd.DataFrame(karsilastirma))
        st.caption("Tum fonlar 45 gun once 100'den baslatilir; boylece fiyat "
                   "buyuklugu farki olmadan getiri kiyaslanir. Dik cikan "
                   "cizgi = yuksek getiri (ve genelde yuksek risk).")

    st.subheader("📝 Gunun Hareket Analizi")
    for kod in FONLAR:
        analiz = fon_gun_analizi(kod)
        if analiz:
            st.markdown(f"<div class='analiz-kutu'>{analiz}</div>",
                        unsafe_allow_html=True)

    st.subheader("💡 Fon Alim-Satim Rehberi")
    st.markdown(f"<div class='tuyo-kutu'>{TUYOLAR_FON}<br><br><i>Bunlar genel "
                "teknik/islevsel kurallardir, kisisel yatirim tavsiyesi "
                "degildir.</i></div>", unsafe_allow_html=True)

    st.subheader("🕐 Valor Hesaplayici")
    try:
        v1, v2, v3, v4 = st.columns(4)
        v_fon = v1.selectbox("Fon", FONLAR, key="valor_fon")
        v_islem = v2.radio("Islem", ["Alim", "Satim"], key="valor_islem",
                           horizontal=True)
        v_tarih = v3.date_input("Emir tarihi", value=bugun, key="valor_tarih")
        v_saat = v4.time_input("Emir saati", value=datetime.now().time(),
                               key="valor_saat")

        def sonraki_is_gunu(tarih):
            tarih += timedelta(days=1)
            while tarih.weekday() >= 5:
                tarih += timedelta(days=1)
            return tarih

        def is_gunu_ekle(tarih, n):
            try:
                n = max(0, int(n))
            except (TypeError, ValueError):
                n = 0
            while tarih.weekday() >= 5:
                tarih = sonraki_is_gunu(tarih)
            for _ in range(n):
                tarih = sonraki_is_gunu(tarih)
            return tarih

        kesme = (v_saat.hour, v_saat.minute) >= KESME_SAATI
        if v_tarih.weekday() >= 5:
            emir_gunu = is_gunu_ekle(v_tarih, 0)
            neden = "hafta sonu oldugu icin"
        elif kesme:
            emir_gunu = sonraki_is_gunu(v_tarih)
            neden = "saat 13:30'dan sonra oldugu icin"
        else:
            emir_gunu, neden = v_tarih, None

        valorler = VALOR.get(v_fon, (1, 2))
        n = int(valorler[0] if v_islem == "Alim" else valorler[1])
        sonuc_gunu = is_gunu_ekle(emir_gunu, n)
        gun_adi = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma",
                   "Cumartesi", "Pazar"]

        mesaj = []
        if neden:
            mesaj.append(f"⏰ Emrin {neden} <b>{emir_gunu.strftime('%d.%m.%Y')} "
                         f"{gun_adi[emir_gunu.weekday()]}</b> gununun emri sayilir.")
        else:
            mesaj.append(f"Emir <b>{emir_gunu.strftime('%d.%m.%Y')} "
                         f"{gun_adi[emir_gunu.weekday()]}</b> gunune islenir.")
        if v_islem == "Alim":
            if n == 0:
                mesaj.append("Bu fonda alim ayni gun (T+0) gerceklesir: paylar "
                             "ayni gunun fiyatiyla hesabina gecer.")
            else:
                mesaj.append(f"Alim valoru <b>T+{n}</b>: paylarin "
                             f"<b>{sonuc_gunu.strftime('%d.%m.%Y')} "
                             f"{gun_adi[sonuc_gunu.weekday()]}</b> gunu, o gunun "
                             "fon fiyatindan hesabina gecer — yani odedigin fiyat "
                             "bugunku degil, o gunku fiyattir.")
        else:
            if n == 0:
                mesaj.append("Bu fonda satis ayni gun (T+0) gerceklesir: paran "
                             "ayni gun hesabina gecer.")
            else:
                mesaj.append(f"Satim valoru <b>T+{n}</b>: paran "
                             f"<b>{sonuc_gunu.strftime('%d.%m.%Y')} "
                             f"{gun_adi[sonuc_gunu.weekday()]}</b> gunu hesabina "
                             "gecer ve satis o gunun fiyatindan olur — dusus "
                             "gunlerinde 'hemen cikis' bu yuzden mumkun degildir.")
        st.markdown("<div class='analiz-kutu'>" + "<br><br>".join(mesaj)
                    + "</div>", unsafe_allow_html=True)
    except Exception as hata:
        st.error(f"Valor hesaplayici gecici bir sorunla karsilasti: {hata}. "
                 "Sayfayi yenileyin; sorun surerse diger bolumler etkilenmez.")
    st.caption("Valorler: TLY/THF/DOH alim T+1 satim T+2, para fonlari T+0 "
               "(genel kurallar; fonun izahnamesinden teyit edin). Resmi "
               "tatiller hesaba katilmaz — tatile denk gelirse bir is gunu "
               "daha ekle. Satista kar uzerinden %17,5 stopaj kesilir.")

def hisse_fonu_sekmesi(kod):
    sepet = SEPETLER[kod]
    st.subheader(f"{kod} — {FON_ACIKLAMA.get(kod, '')}")
    st.caption(f"Sepet: aylik KAP raporundaki {len(sepet)} hisse "
               f"(fonun ~%{sum(sepet.values()):.0f}'i).")

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
        sertler = gecerli["Gun"].apply(hareket_turu)
        k4.metric("Taban / Tavan / Ayarlama?",
                  f"{(sertler=='taban').sum()} / {(sertler=='tavan').sum()} "
                  f"/ {(sertler=='ayarlama?').sum()}")

    t_fon = FON_VERI.get(kod)
    if t_fon is not None and len(t_fon) > 2:
        st.markdown("**Fonun fiyat seyri (son 45 gun, resmi TEFAS)**")
        st.line_chart(t_fon.set_index("TARIH")["FIYAT"])

    goster = alt[["Hisse", "Agirlik", "Fiyat", "Gun", "Hafta", "Ay",
                  "SMA20", "RSI", "Sinyal"]].rename(columns={
        "Agirlik": "Agirlik %", "Fiyat": "Fiyat (TL)", "Gun": "Gun %",
        "Hafta": "Hafta %", "Ay": "Ay %", "SMA20": "SMA20 Fark %"})
    st.dataframe(goster.style
                   .map(sayi_renk, subset=["Gun %", "Hafta %", "Ay %", "SMA20 Fark %"])
                   .map(sinyal_renk, subset=["Sinyal"])
                   .format({"Fiyat (TL)": "{:.2f}", "Gun %": "{:+.2f}",
                            "Hafta %": "{:+.2f}", "Ay %": "{:+.2f}",
                            "SMA20 Fark %": "{:+.2f}", "RSI": "{:.1f}",
                            "Agirlik %": "{:.1f}"}, na_rep="—"),
                 use_container_width=True, hide_index=True,
                 height=38 * len(alt) + 60)

    if not gecerli.empty:
        st.markdown("**Gunluk degisim (%)**")
        st.bar_chart(gecerli.set_index("Hisse")["Gun"])

    st.subheader("🧠 Hisse Yorumlari")
    st.markdown("<div class='analiz-kutu'>"
                + "<br><br>".join(hisse_yorumlari(kod))
                + "</div>", unsafe_allow_html=True)
    st.subheader("💡 Hisse Alim-Satim Rehberi")
    st.markdown(f"<div class='tuyo-kutu'>{TUYOLAR_HISSE}<br><br><i>Genel "
                "teknik kurallardir, kisisel yatirim tavsiyesi degildir.</i>"
                "</div>", unsafe_allow_html=True)

def para_fonu_sekmesi(kod):
    st.subheader(f"{kod} — {FON_ACIKLAMA.get(kod, '')}")
    st.info("Para piyasasi fonu: portfoyunde hisse degil mevduat/repo bulunur; "
            "bu yuzden hisse analizi yerine fonun kendi seyri gosterilir.")
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
    st.markdown("**Fiyat seyri (son 45 gun)**")
    st.line_chart(t.set_index("TARIH")["FIYAT"])
    st.markdown("**Gunluk getiri (%)**")
    st.bar_chart(t.dropna(subset=["Degisim"]).set_index("TARIH")["Degisim"])
    st.markdown("<div class='tuyo-kutu'><b>Para fonu tuyolari:</b> Bu fonlar "
                "'park yeri' islevi gorur — nakiti beklerken degerlendirmek "
                "icindir, getirisi mevduata yakindir. Riskli fonlardan cikip "
                "beklemek istedigin donemde iyi bir ara duraktir. Getiri "
                "grafigi duzenli olmali; ani sicramalar veri hatasidir."
                "<br><br><i>Yatirim tavsiyesi degildir.</i></div>",
                unsafe_allow_html=True)

for i, kod in enumerate(FONLAR, start=1):
    with sekmeler[i]:
        if kod in SEPETLER:
            hisse_fonu_sekmesi(kod)
        else:
            para_fonu_sekmesi(kod)
