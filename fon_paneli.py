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

import io
import re
import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

FONLAR = ["TLY", "THF", "DOH", "TP2", "PRY", "PNU"]
GUN_ADLARI = {0: "Pzt", 1: "Sali", 2: "Cars", 3: "Pers", 4: "Cuma"}

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
SEPETLER = {k: dict(v) for k, v in YEDEK_SEPETLER.items()}
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

# ---------- Kullanicinin ekledigi fonlar (?ekfon=AFA,MAC) ----------
def _ek_fonlar_oku():
    ham = st.query_params.get("ekfon", "")
    kodlar = []
    for parca in ham.split(","):
        parca = re.sub(r"[^A-Za-z0-9]", "", parca).upper()
        if 2 <= len(parca) <= 6 and parca not in FONLAR and parca not in kodlar:
            kodlar.append(parca)
    return kodlar[:6]

EK_FONLAR = _ek_fonlar_oku()
FONLAR = FONLAR + EK_FONLAR

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
oto_sepet = st.sidebar.toggle("🤖 Sepetleri KAP'tan otomatik al", value=True,
                              help="Kapatirsan guvenilir yedek listeler "
                                   "kullanilir. Sorun aninda kapat.")
aralik = st.sidebar.slider("Yenileme araligi (dakika)", 1, 30, 5)
GUN_MOD = st.sidebar.radio("Gun sutunlari icerigi",
                           ["% Degisim", "Kapanis TL"],
                           help="Kapanis modunda gun hucrelerinde o gunun "
                                "fon fiyati gorunur; bugunun hucresi "
                                "~tahmini kapanistir.")
if not duraklat:
    st_autorefresh(interval=aralik * 60 * 1000, key="oto_yenile")
else:
    st.sidebar.warning("Otomatik yenileme KAPALI — isin bitince anahtari kapat.")

with st.sidebar.expander("➕ Fon ekle / cikar"):
    with st.form("ekfon_formu"):
        yeni_fon = st.text_input("TEFAS fon kodu", placeholder="orn. AFA")
        f1, f2 = st.columns(2)
        fon_ekle = f1.form_submit_button("Ekle", use_container_width=True)
        fon_temizle = f2.form_submit_button("Hepsini cikar",
                                            use_container_width=True)
    if fon_ekle and yeni_fon.strip():
        kod_yeni = re.sub(r"[^A-Za-z0-9]", "", yeni_fon).upper()
        if 2 <= len(kod_yeni) <= 6 and kod_yeni not in FONLAR:
            st.query_params["ekfon"] = ",".join(EK_FONLAR + [kod_yeni])
            st.rerun()
    if fon_temizle and "ekfon" in st.query_params:
        del st.query_params["ekfon"]
        st.rerun()
    st.caption("Ekli: " + (", ".join(EK_FONLAR) if EK_FONLAR else "yok")
               + ". Eklenen fonlar resmi TEFAS verisiyle izlenir (fiyat, "
               "getiri, yatirimci, tutar, K/Z, alarm); gun ici ~ tahmin "
               "sadece sepeti tanimli fonlarda calisir. Liste adrese "
               "islenir, yer imiyle kalicidir.")

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

# ---------- WhatsApp Bildirimlerim (herkes icin, GitHub'siz) ----------
st.sidebar.markdown("---")
st.sidebar.subheader("📲 WhatsApp Bildirimlerim")
with st.sidebar.form("wa_formu"):
    wa_tel_giris = st.text_input("Numaran (ulke koduyla)",
                                 value=st.query_params.get("wa", ""),
                                 placeholder="+905xxxxxxxxx")
    wa_key_giris = st.text_input("CallMeBot anahtarin",
                                 value=st.query_params.get("wakey", ""),
                                 type="password", placeholder="123456")
    w1, w2 = st.columns(2)
    wa_kaydet = w1.form_submit_button("💾 Kaydet", use_container_width=True)
    wa_test = w2.form_submit_button("📨 Ozet at", use_container_width=True)
if wa_kaydet or wa_test:
    if wa_tel_giris.strip() and wa_key_giris.strip():
        st.query_params["wa"] = wa_tel_giris.strip()
        st.query_params["wakey"] = wa_key_giris.strip()
    else:
        for _a in ("wa", "wakey"):
            if _a in st.query_params:
                del st.query_params[_a]
WA_TEL = st.query_params.get("wa", "")
WA_KEY = st.query_params.get("wakey", "")
if wa_test:
    st.session_state["wa_ozet_iste"] = True
with st.sidebar.expander("❓ Anahtar nasil alinir? (2 dk)"):
    st.markdown(
        "**1.** Rehberine su numarayi kaydet: **+34 623 80 11 90** "
        "(CallMeBot'un guncel WhatsApp botu).\n\n"
        "**2.** WhatsApp'tan ona su mesaji gonder:\n"
        "`I allow callmebot to send me messages`\n\n"
        "**3.** Bot sana *'Your APIKEY is 123456'* diye anahtarini yollar — "
        "yukaridaki kutulara numarani ve bu anahtari yazip **Kaydet**'e bas, "
        "**📨 Ozet at** ile dene.\n\n"
        "Kaydettikten sonra **bu sayfa acik oldugu surece** esik asimi, "
        "taban ve cikis alarmlari otomatik WhatsApp'ina gelir (ayni alarm "
        "gunde 1 kez). Bilgilerin bu sayfanin adresine islenir: adresi yer "
        "imine eklersen hep hazir gelir; anahtarin sana ozel oldugu icin "
        "linki kimseyle paylasma.")

def whatsapp_gonder(tel, anahtar, metin):
    """(basarili_mi, detay) doner — detay CallMeBot'un gercek yaniti."""
    tel = (tel or "").strip().replace(" ", "")
    adaylar = [tel]
    if tel.startswith("+"):
        adaylar.append(tel[1:])      # bazi durumlar + isaretini sevmez
    else:
        adaylar.insert(0, "+" + tel)
    son_detay = ""
    for aday in adaylar:
        try:
            r = requests.get(
                "https://api.callmebot.com/whatsapp.php",
                params={"phone": aday, "apikey": anahtar.strip(),
                        "text": metin},
                timeout=60)           # CallMeBot yavas olabiliyor
            govde = (r.text or "").strip()
            if r.status_code == 200 and "ERROR" not in govde.upper():
                return True, govde[:120]
            son_detay = f"HTTP {r.status_code}: {govde[:120]}"
        except Exception as e:
            son_detay = f"{type(e).__name__}: {str(e)[:120]}"
    return False, son_detay

# ---------- Kisisel alarm esikleri (fon bazli, kullanici belirler) ----------
_RISK_ESIK = {7: -3.5, 6: -2.5, 5: -2.5, 4: -1.5, 3: -1.5, 2: -0.1, 1: -0.1}
VARSAYILAN_ESIK = {k: _RISK_ESIK[RISK_YEDEK.get(k, 5)] for k in FONLAR}
with st.sidebar.expander("🔔 Alarm esiklerim (%)"):
    with st.form("esik_formu"):
        _esikler = {}
        for _kod in FONLAR:
            try:
                _ev = float(st.query_params.get(f"{_kod}e",
                                                VARSAYILAN_ESIK[_kod]))
            except (TypeError, ValueError):
                _ev = VARSAYILAN_ESIK[_kod]
            _esikler[_kod] = st.number_input(
                f"{_kod} dusus esigi", min_value=-20.0, max_value=0.0,
                value=_ev, step=0.5, format="%.1f")
        if st.form_submit_button("💾 Esikleri kaydet",
                                 use_container_width=True):
            for _kod, _v in _esikler.items():
                if abs(_v - VARSAYILAN_ESIK[_kod]) > 1e-9:
                    st.query_params[f"{_kod}e"] = f"{_v:g}"
                elif f"{_kod}e" in st.query_params:
                    del st.query_params[f"{_kod}e"]
    st.caption("Fonun gunluk degisimi esigine dusunce WhatsApp alarmi gelir. "
               "Ornek: -3,5 yazarsan %-3,5 ve altinda uyarilirsin. 0 = her "
               "eksi gunde uyar; -20 = o fon icin fiilen kapali. Varsayilan "
               "degerler fonun risk seviyesine goredir; degistirdiklerin "
               "adrese islenir, yer imiyle kalici olur.")
KULLANICI_ESIK = _esikler

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

FONPARAM_ADRESLER = ["https://api.fonparam.com",
                     "https://fonparam.apimapi.net"]

def _fonparam(kod, gun):
    bitis = datetime.now()
    baslangic = bitis - timedelta(days=gun)
    veri, son_hata = None, None
    for adres in FONPARAM_ADRESLER:
        try:
            r = requests.get(
                f"{adres}/funds/{kod}/historical",
                params={"start_date": baslangic.strftime("%Y-%m-%d"),
                        "end_date": bitis.strftime("%Y-%m-%d")},
                headers={"User-Agent": TARAYICI["User-Agent"]}, timeout=10)
            if r.status_code == 200:
                veri = r.json()
                break
        except Exception as e:
            son_hata = e
            continue
    if veri is None:
        raise RuntimeError(f"FonParam ulasilemedi: {son_hata}")
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

import json as _json

def _onbellek_yaz(kod, t):
    try:
        kayit = t.copy()
        kayit["TARIH"] = kayit["TARIH"].dt.strftime("%Y-%m-%d")
        with open(f"/tmp/fon_{kod}.json", "w") as f:
            _json.dump(kayit.to_dict(orient="records"), f)
    except Exception:
        pass

def _onbellek_oku(kod):
    try:
        with open(f"/tmp/fon_{kod}.json") as f:
            kayitlar = _json.load(f)
        t = pd.DataFrame(kayitlar)
        t["TARIH"] = pd.to_datetime(t["TARIH"])
        for k in ["FIYAT", "KISISAYISI", "PORTFOYBUYUKLUK"]:
            t[k] = pd.to_numeric(t.get(k), errors="coerce")
        t = t.sort_values("TARIH").reset_index(drop=True)
        t["Degisim"] = t["FIYAT"].pct_change() * 100
        return t if len(t) >= 2 else None
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def fon_gecmisi(kod, gun=45):
    try:
        t = _fonparam(kod, gun)
        if t is not None and len(t) >= 2:
            _onbellek_yaz(kod, t)
            return t, "FonParam"
    except Exception:
        pass
    for site, ad in KAYNAKLAR:
        try:
            t = _tefas(kod, gun, site)
            if t is not None and len(t) >= 2:
                _onbellek_yaz(kod, t)
                return t, ad
        except Exception:
            continue
    t = _onbellek_oku(kod)
    if t is not None:
        son_g = t["TARIH"].iloc[-1].strftime("%d.%m")
        return t, f"onbellek ({son_g} verisi)"
    return None, None

# ---------- Otomatik sepet guncelleme (aylik KAP raporundan) ----------
_SEPET_KARA_LISTE = {"TOPLAM", "TARIH", "FONUN", "HISSE", "PAYLAR", "BIST",
                     "VADELI", "TAKAS", "REPO", "DIGER", "TERS", "DEVLET",
                     "OZEL", "YATIRIM", "MEVDUAT", "KATILMA", "SAYFA",
                     "SANAYI", "ENERJI", "GIDA", "DEMIR", "CELIK",
                     "BANKA", "METAL", "TARIM", "INSAAT", "TURIZM"}

@st.cache_data(ttl=86400, show_spinner=False)
def sepet_otomatik(kod):
    """Son aylik KAP portfoy raporunu (Fintables arsivi) indirip
    hisse agirliklarini cikarir. Basarisizsa (None, None) doner."""
    try:
        import pdfplumber
    except Exception:
        return None, None
    simdi = simdi_tr()
    donemler = []
    for geri in range(2):
        ay, yil = simdi.month - geri, simdi.year
        if ay < 1:
            ay, yil = ay + 12, yil - 1
        donemler.append(f"{yil}.{ay:02d}")
    for donem in donemler:
        try:
            r = requests.get(
                "https://storage.fintables.com/media/uploads/"
                f"kap-attachments/{kod}_{donem}.pdf",
                headers={"User-Agent": TARAYICI["User-Agent"]}, timeout=8)
            if r.status_code != 200 or r.content[:4] != b"%PDF":
                continue
            metin = ""
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                for sayfa in pdf.pages:
                    metin += (sayfa.extract_text() or "") + "\n"
            agirliklar = {}
            for satir in metin.split("\n"):
                m = re.match(r"^([A-Z]{4,6})\s", satir)
                if not m or m.group(1) in _SEPET_KARA_LISTE:
                    continue
                yuzdeler = re.findall(r"(\d{1,2},\d{2})", satir)
                if not yuzdeler:
                    continue
                try:
                    w = float(yuzdeler[-1].replace(",", "."))
                except ValueError:
                    continue
                if 0 < w <= 60:
                    agirliklar[m.group(1)] = agirliklar.get(m.group(1), 0) + w
            toplam = sum(agirliklar.values())
            if len(agirliklar) >= 3 and 25 <= toplam <= 110:
                return agirliklar, donem
        except Exception:
            continue
    return None, None

SEPET_KAYNAK = {}
for _kod in list(SEPETLER):
    _oto, _donem = (sepet_otomatik(_kod) if oto_sepet else (None, None))
    if _oto:
        SEPETLER[_kod] = _oto
        SEPET_KAYNAK[_kod] = f"KAP {_donem} raporu (otomatik)"
    else:
        SEPET_KAYNAK[_kod] = "elle girilen yedek liste"

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

# Otomatik sepet dogrulamasi: Yahoo'da karsiligi olmayan satirlar elenir;
# kalan kapsam yetersizse guvenilir yedek listeye donulur.
_gecerli_hisseler = set(METRIK.dropna(subset=["Fiyat"])["Hisse"])
for _kod in list(SEPETLER):
    if not SEPET_KAYNAK.get(_kod, "").startswith("KAP"):
        continue
    _temiz = {h: w for h, w in SEPETLER[_kod].items() if h in _gecerli_hisseler}
    _atilan = len(SEPETLER[_kod]) - len(_temiz)
    if len(_temiz) >= 3 and sum(_temiz.values()) >= 25:
        SEPETLER[_kod] = _temiz
        if _atilan:
            SEPET_KAYNAK[_kod] += f", {_atilan} suheli satir elendi"
    else:
        SEPETLER[_kod] = dict(YEDEK_SEPETLER[_kod])
        SEPET_KAYNAK[_kod] = "elle girilen yedek liste (otomatik dogrulanamadi)"

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
            parca = v.split("·")[0].strip().replace("~", "")
            if not parca.startswith(("+", "-")):
                return ""          # fiyat gibi isaretsiz degerler boyanmaz
            s = float(parca.replace(",", "."))
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
    kapanislar = {r["TARIH"].date(): float(r["FIYAT"])
                  for _, r in t.iterrows() if pd.notna(r["FIYAT"])}

    def kap_str(f, tahmin=False):
        return ("~" if tahmin else "") + tr_sayi(f, 4 if f < 10 else 0)

    for gun_no, ad in GUN_ADLARI.items():
        hedef = pazartesi + timedelta(days=gun_no)
        if hedef in resmi_gunler:
            if GUN_MOD == "Kapanis TL" and hedef in kapanislar:
                satir[ad] = kap_str(kapanislar[hedef])
            else:
                satir[ad] = yuzde_str(resmi_gunler[hedef])
        else:
            th = sepet_tahmini_tarih(kod, hedef)
            if th is None and kod in MEVDUAT_BENZERI and hedef <= bugun and hedef > son_resmi_tarih:
                th = float(son["Degisim"])
            if th is not None:
                if GUN_MOD == "Kapanis TL":
                    if hedef == bugun and pd.notna(son["FIYAT"]):
                        satir[ad] = kap_str(float(son["FIYAT"]) * (1 + th / 100),
                                            tahmin=True)
                    else:
                        satir[ad] = "—"
                else:
                    satir[ad] = yuzde_str(th, True)
            else:
                satir[ad] = "—"

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

# ---------- Ziyaretci WhatsApp bildirimleri (sayfa acikken calisir) ----------

def karne_ciftleri(kod):
    """Fonun gun gun (resmi, tahmin, sapma) ciftleri — sekme ve alarm ortak."""
    t = FON_VERI.get(kod)
    if t is None or len(t) <= 5 or DEG.empty or kod not in SEPETLER:
        return None
    ciftler = []
    for _, r in t.iterrows():
        if pd.isna(r["Degisim"]):
            continue
        th = sepet_tahmini_tarih(kod, r["TARIH"].date())
        if th is not None:
            ciftler.append(dict(Tarih=r["TARIH"], Resmi=float(r["Degisim"]),
                                Tahmin=th, Sapma=th - float(r["Degisim"])))
    return pd.DataFrame(ciftler) if len(ciftler) >= 5 else None

def ozet_metni():
    parcalar = []
    for kod in FONLAR:
        b = FON_ANALIZ.get(kod)
        if b and b.get("gunluk") is not None:
            isaret = "~" if b.get("tahmin") else ""
            parcalar.append(f"*{kod}*: {isaret}%{b['gunluk']:+.2f}")
        else:
            parcalar.append(f"*{kod}*: veri yok")
    return ("📊 *Fon Ozeti* (" + simdi_tr().strftime("%d.%m %H:%M")
            + " TR)\n" + "\n".join(parcalar)
            + "\n_Yatirim tavsiyesi degildir._")

if WA_TEL and WA_KEY:
    # 1) Istek uzerine ozet
    if st.session_state.pop("wa_ozet_iste", False):
        ok, detay = whatsapp_gonder(WA_TEL, WA_KEY, ozet_metni())
        if ok:
            st.sidebar.success("Ozet WhatsApp'ina gonderildi ✅ (Mesaj "
                               "birkac dakika gecikebilir.)")
        else:
            st.sidebar.error(f"Gonderilemedi — CallMeBot yaniti: {detay}")
    # 2) Otomatik alarmlar (ayni alarm gunde 1 kez, bu oturumda)
    bugun_a = str(bugun)
    gidenler = st.session_state.setdefault("wa_gidenler", {})
    gidenler = {bugun_a: gidenler.get(bugun_a, [])}
    st.session_state["wa_gidenler"] = gidenler
    alarmlar = []
    for kod in FONLAR:
        b = FON_ANALIZ.get(kod, {})
        gunluk = b.get("gunluk")
        esik = KULLANICI_ESIK.get(kod, VARSAYILAN_ESIK.get(kod, -2.0))
        if gunluk is not None and gunluk <= esik \
                and f"{kod}-esik" not in gidenler[bugun_a]:
            alarmlar.append(f"🔴 *{kod}* gunluk %{gunluk:+.2f} — senin esigin "
                            f"(%{esik:g}) asildi.")
            gidenler[bugun_a].append(f"{kod}-esik")
        sepet = SEPETLER.get(kod, {})
        if sepet and not METRIK.empty:
            alt_a = METRIK[METRIK["Hisse"].isin(sepet)].dropna(subset=["Gun"])
            tabanlar = alt_a[(alt_a["Gun"] <= -9.5)
                             & (alt_a["Gun"] > -10.5)]["Hisse"].tolist()
            if tabanlar and f"{kod}-taban" not in gidenler[bugun_a]:
                alarmlar.append(f"🟠 *{kod}* sepetinde taban: "
                                + ", ".join(tabanlar))
                gidenler[bugun_a].append(f"{kod}-taban")
        t_a = FON_VERI.get(kod)
        if kod in SEPETLER and t_a is not None and len(t_a) >= 2:
            ky = t_a["KISISAYISI"].iloc[-1] - t_a["KISISAYISI"].iloc[-2]
            kt = t_a["PORTFOYBUYUKLUK"].iloc[-1] - t_a["PORTFOYBUYUKLUK"].iloc[-2]
            if pd.notna(ky) and pd.notna(kt) and ky < 0 and kt < 0 \
                    and f"{kod}-cikis" not in gidenler[bugun_a]:
                alarmlar.append(f"🟡 *{kod}*: yatirimci ve tutar birlikte "
                                "eksi — cikis sinyali.")
                gidenler[bugun_a].append(f"{kod}-cikis")
        # Karne sismografi: sapma aniden buyudu = sepet kaymis olabilir
        kc = karne_ciftleri(kod)
        if kc is not None and len(kc) >= 10 \
                and f"{kod}-karne" not in gidenler[bugun_a]:
            son3 = kc["Sapma"].tail(3).abs().mean()
            onceki = kc["Sapma"].iloc[:-3].abs().mean()
            if son3 > 1.0 and son3 > 2 * max(onceki, 0.2):
                alarmlar.append(
                    f"🟣 *{kod}*: tahmin sapmasi son 3 gunde ±{son3:.1f} "
                    f"puana cikti (onceki ort. ±{onceki:.1f}) — fon sepetini "
                    "rapor disinda degistirmis olabilir, temkinli izle.")
                gidenler[bugun_a].append(f"{kod}-karne")
    if alarmlar:
        ok, _detay = whatsapp_gonder(
            WA_TEL, WA_KEY,
            "⚠ *Fon Alarm* (" + simdi_tr().strftime("%d.%m %H:%M")
            + " TR)\n" + "\n".join(alarmlar)
            + "\n_Yatirim tavsiyesi degildir._")
        st.toast("WhatsApp alarmi gonderildi 📲" if ok
                 else f"Alarm gonderilemedi: {_detay[:60]}")

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
    try:
        _xbuf = io.BytesIO()
        fon_df.to_excel(_xbuf, index=False, sheet_name="Fonlar")
        st.download_button("📥 Tabloyu Excel olarak indir", _xbuf.getvalue(),
                           file_name=f"fon_takip_{bugun}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument"
                                ".spreadsheetml.sheet")
    except Exception:
        st.download_button("📥 Tabloyu CSV olarak indir",
                           fon_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name=f"fon_takip_{bugun}.csv", mime="text/csv")

    st.subheader("📈 Fonlarin Getiri Karsilastirmasi")
    donem = st.radio("Donem", ["1 Hafta", "1 Ay", "Tumu (45 gun)"],
                     horizontal=True, key="grafik_donem", index=1)
    donem_gun = {"1 Hafta": 5, "1 Ay": 21, "Tumu (45 gun)": 9999}[donem]
    getiri_cizgi, donem_getiri = {}, {}
    for kod in FONLAR:
        t = FON_VERI.get(kod)
        if t is not None and len(t) > 2:
            kesit = t.tail(donem_gun + 1)
            if len(kesit) >= 2 and pd.notna(kesit["FIYAT"].iloc[0]):
                seri = (kesit.set_index("TARIH")["FIYAT"]
                        / float(kesit["FIYAT"].iloc[0]) - 1) * 100
                getiri_cizgi[kod] = seri
                donem_getiri[kod] = float(seri.iloc[-1])
    # Kiyas cizgisi: BIST 100
    try:
        @st.cache_data(ttl=900, show_spinner=False)
        def _bist100():
            df = yf.download("XU100.IS", period="3mo", interval="1d",
                             progress=False, auto_adjust=True)
            return df["Close"].squeeze().dropna()
        _xu = _bist100().tail(donem_gun + 1)
        if len(_xu) >= 2:
            _xus = (_xu / float(_xu.iloc[0]) - 1) * 100
            _xus.index = pd.to_datetime(_xus.index)
            getiri_cizgi["BIST 100"] = _xus
            donem_getiri["BIST 100"] = float(_xus.iloc[-1])
    except Exception:
        pass
    if getiri_cizgi:
        g1, g2 = st.columns([3, 2])
        with g1:
            st.markdown(f"**Gun gun birikimli getiri — {donem} (%)**")
            st.line_chart(pd.DataFrame(getiri_cizgi))
            st.caption("Her cizgi 0'dan baslar; cizginin geldigi seviye = o "
                       "fona donem basinda para koysaydin bugune kadarki "
                       "toplam kazancin (%). Ornegin cizgi 12'deyse donem "
                       "getirisi %12 demektir.")
        with g2:
            st.markdown(f"**Donem sonu getiri — {donem} (%)**")
            st.bar_chart(pd.Series(donem_getiri).sort_values(ascending=False))
            st.caption("Ayni bilginin ozeti: donem boyunca hangi fon toplamda "
                       "ne kazandirdi/kaybettirdi.")

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

    with st.expander("📲 WhatsApp Bildirimleri Nasil Kurulur?"):
        st.markdown("""
Iki yol var — cogu kullanici icin **Yol A yeterli** ve GitHub gerektirmez:

---
### Yol A — Sadece bu siteyle (herkes icin, ~3 dk)

**1.** Rehberine su numarayi kaydet: **+34 623 80 11 90** (CallMeBot botu)

**2.** WhatsApp'tan ona su mesaji gonder:
`I allow callmebot to send me messages`

**3.** Bot sana *"Your APIKEY is 123456"* diye kisisel anahtarini dondurur.

**4.** Bu sitenin **kenar cubugundaki 📲 WhatsApp Bildirimlerim** bolumune
numarani ve anahtarini yaz → **Kaydet** → **📨 Ozet at** ile test et.

Artik **bu sayfa acik oldugu surece** (bilgisayarda arka plandaki sekme de
sayilir) risk esigi asimi 🔴, sepette taban 🟠 ve fon cikisi 🟡 alarmlari
otomatik WhatsApp'ina gelir — ayni alarm gunde 1 kez, spam yok. Bilgilerin
sayfanin adresine islenir: adresi yer imine ekle, anahtarin sana ozel oldugu
icin linki paylasma.

---
### Yol B — Site kapaliyken de mesaj (repo sahibi icin, GitHub Actions)

Sayfa kapaliyken de alarm ve her aksam 18:45 gun sonu ozeti istiyorsan:

**1.** Yol A'daki 1-3. adimlarla anahtarini al.

**2.** GitHub'da repo → **Settings → Secrets and variables → Actions →
New repository secret** ile iki secret olustur:
`WHATSAPP_PHONE` = +905xxxxxxxxx ve `CALLMEBOT_APIKEY` = anahtarin.

**3.** `alarm_kontrol.py` dosyasini reponun ana dizinine, `alarm.yml`
dosyasini `.github/workflows/` klasorune yukle.

**4.** **Actions** sekmesi → *Fon Alarmlari* → **Run workflow** → `ozet`
yazip calistir; 1-2 dakikada test mesajin gelir. Sonrasi otomatik: hafta ici
10:00-17:30 arasi her 30 dk kontrol + 18:45 gun sonu ozeti.

---
Alarm esiklerini kenar cubugundaki **🔔 Alarm esiklerim** bolumunden fon fon
kendin belirlersin — varsayilanlar risk seviyesine goredir (7/7'de %-3,5,
para fonlarinda %-0,1) ama son soz senin. Yol B'nin esikleri ise
`alarm_kontrol.py` icindeki ESIK sozlugunden degistirilir.

*Not: CallMeBot gonullu bir servistir, resmi Meta urunu degildir — nadiren
gecikebilir. Kritik kararlari sadece mesaja degil, siteye bakarak ver.*
""")

def hisse_fonu_sekmesi(kod):
    sepet = SEPETLER[kod]
    st.subheader(f"{kod} — {FON_ACIKLAMA.get(kod, '')}")
    st.caption(f"Sepet: {SEPET_KAYNAK.get(kod, '')} — {len(sepet)} hisse "
               f"(fonun ~%{sum(sepet.values()):.0f}'i). Her ay basinda yeni "
               "rapor yayinlaninca otomatik yenilenir.")

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

    # ---- Tahmin Isabet Karnesi ----
    karne = karne_ciftleri(kod)
    if karne is not None:
        if True:
            mad = karne["Sapma"].abs().mean()
            ayni_yon = ((karne["Resmi"] * karne["Tahmin"]) > 0) | \
                       ((karne["Resmi"].abs() < 0.1) & (karne["Tahmin"].abs() < 0.1))
            yon_isabet = ayni_yon.mean() * 100
            en_kotu = karne.loc[karne["Sapma"].abs().idxmax()]
            with st.expander(f"🎯 Tahmin Isabet Karnesi ({len(karne)} gun)"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Ortalama sapma", f"±{mad:.2f} puan",
                          help="~ tahmin ile aksam aciklanan resmi rakam "
                               "arasindaki ortalama fark")
                c2.metric("Yon isabeti", f"%{yon_isabet:.0f}",
                          help="Tahminin gunu dogru yonde (arti/eksi) "
                               "bildigi gunlerin orani")
                c3.metric("En buyuk sapma",
                          f"{en_kotu['Sapma']:+.2f} puan",
                          delta=en_kotu["Tarih"].strftime("%d.%m"),
                          delta_color="off")
                st.markdown("**Resmi (mavi) vs Tahmin (kirmizi) — gunluk %**")
                st.line_chart(karne.set_index("Tarih")[["Resmi", "Tahmin"]],
                              color=["#c62828", "#1f4e79"])
                st.caption("Karne, bugunku sepet agirliklariyla geriye donuk "
                           "hesaplanir; sepet her ay degistigi icin eski "
                           "gunlerde sapma oldugundan buyuk gorunebilir. "
                           "Bedelsiz/bolunme gunleri de sapmayi sisirir. "
                           f"Sepet fonun ~%{sum(sepet.values()):.0f}'ini "
                           "kapsar — kalan kisim tahmine dahil degildir. "
                           "Kisacasi: ~ isaretli rakamlara ortalama sapma "
                           "kadar pay birakarak bak.")

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

def genel_fon_sekmesi(kod):
    st.subheader(f"{kod} — {FON_ACIKLAMA.get(kod, 'Kullanicinin ekledigi fon')}")
    t = FON_VERI.get(kod)
    if t is None or len(t) < 3:
        st.warning("Bu fon kodu icin TEFAS verisi bulunamadi — kodu kontrol "
                   "et (kenar cubugu ➕ Fon ekle / cikar).")
        return
    son = t.iloc[-1]
    k1, k2, k3 = st.columns(3)
    k1.metric("Son fiyat (TL)", tr_sayi(son["FIYAT"], 4 if son["FIYAT"] < 10 else 2))
    k2.metric("Son gunluk getiri", "%" + yuzde_str(float(son["Degisim"])))
    if len(t) > 21 and pd.notna(t["FIYAT"].iloc[-22]):
        aylik = (float(son["FIYAT"]) / float(t["FIYAT"].iloc[-22]) - 1) * 100
        k3.metric("Aylik getiri", "%" + yuzde_str(aylik))
    st.markdown("**Fiyat seyri (son 45 gun, resmi TEFAS)**")
    st.line_chart(t.set_index("TARIH")["FIYAT"])
    st.markdown("**Gunluk getiri (%)**")
    st.bar_chart(t.dropna(subset=["Degisim"]).set_index("TARIH")["Degisim"])
    st.info("Bu fon kullanici tarafindan eklendi: resmi verilerle izlenir "
            "ama portfoy sepeti tanimli olmadigi icin gun ici ~ tahmin ve "
            "hisse analizi bu fonda yoktur.")

for i, kod in enumerate(FONLAR, start=1):
    with sekmeler[i]:
        if kod in SEPETLER:
            hisse_fonu_sekmesi(kod)
        elif kod in MEVDUAT_BENZERI:
            para_fonu_sekmesi(kod)
        else:
            genel_fon_sekmesi(kod)
