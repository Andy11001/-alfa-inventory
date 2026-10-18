# -*- coding: utf-8 -*-
"""
Wspólna obsługa cenników SCCF/FCCF marek ex-FCA (Fiat, Jeep, Abarth)
=====================================================================

Marki ex-FCA nie mają API configv3 (to rodzina ex-PSA: Peugeot/Opel/Citroën/DS).
Ich konfigurator "omni" czyta statyczne JSON-y wystawione na stronie marki:

  katalog modeli:  https://{host}/sccf/prod/{slug}/publish/data/fccf_mv/scope/{MARKET}{LANG}{brand}.json
  jeden model:     https://{host}/sccf/prod/{slug}/publish/data/fccf_mv{nsbpath}/CM_T5_{MARKET}{LANG}{brand}_{cod}.json

Kody marek (rynek PL = 3123, język pl = D): Fiat 00, Jeep 57, Abarth 66,
Alfa Romeo 83. Kod Abartha (66) wyszedł z przeglądu zakresu — nie jest
zgadywalny z nazwy, więc siedzi w konfiguracji marki, nie w kodzie.

CENY: `Vehs[].PriceArray[0]` to cena NETTO. Strony marek pokazują brutto,
czyli netto × 1,23 (zweryfikowane: Avenger BEV 137 723,58 → 169 400 zł,
dokładnie tyle, ile podaje jeep.pl). Stąd `to_brutto()` zamiast ślepego
przepisywania PriceArray.

ZDJĘCIA: serwis renderów konfiguratora (api.omnichannel.stla-aws.net/images/v1)
wymaga autoryzacji, a og:image stron modeli jest zepsute (fiat.pl podaje
grafikę Lancii, jeep.pl sam adres domeny). Zostają karty "gamy modeli" ze
strony głównej i zdjęcia z biblioteki /content/dam/ stron modeli — w tej
kolejności. Abarth nie ma ani jednego, ani drugiego i idzie bez zdjęć.

Strony marek stoją za Akamai i odrzucają zwykłe `requests` (HTTP 403) —
dlatego całość idzie przez curl_cffi z podszyciem pod TLS Chrome'a, tak jak
scrapers/spoticar_inventory.py.
"""
import html as html_lib
import re
import unicodedata

from bs4 import BeautifulSoup
from curl_cffi import requests as cr

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

MARKET_PL = "3123"
LANG_PL = "D"
VAT_RATE = 1.23
CURRENT_YEAR = "2026"

# Format feedu modelowego — wspólny z peugeot_model.py / opel_model.py / ds_model.py
FIELDNAMES = [
    "vehicle_id", "title", "description", "rodzaj", "make", "model", "year",
    "link", "image_link", "exterior_color", "additional_image_link", "trim",
    "offer_disclaimer", "offer_disclaimer_url", "price", "offer_type",
    "term_length", "offer_term_qualifier", "amount_price", "amount_percentage",
    "amount_qualifier", "downpayment", "downpayment_qualifier",
    "emission_disclaimer", "emission_disclaimer_url",
    "emission_overlay_disclaimer", "emission_image_link", "fuel_type",
]


def make_session():
    """curl_cffi z podszyciem pod Chrome — bez tego Akamai zwraca 403."""
    return cr.Session(impersonate="chrome")


def to_brutto(price_net_str):
    """PriceArray[0] (netto, str) -> cena brutto w pełnych złotych."""
    try:
        return int(round(float(price_net_str) * VAT_RATE))
    except (TypeError, ValueError):
        return 0


# --- Katalog: scope -> modele -> wersje ------------------------------------

def _sccf_base(host, slug):
    return f"https://{host}/sccf/prod/{slug}/publish/data/fccf_mv"


def fetch_scope(session, host, slug, brand_code):
    """Katalog modeli handlowych marki (comMods)."""
    url = f"{_sccf_base(host, slug)}/scope/{MARKET_PL}{LANG_PL}{brand_code}.json"
    r = scraper_utils.fetch_with_retry(session, url, timeout=40)
    return r.json()


def fetch_com_mod(session, host, slug, brand_code, com_mod):
    """Dane jednego modelu handlowego (wersje + ceny). None gdy się nie udało —
    jeden zepsuty model nie może wywalić całego feedu."""
    nsb = com_mod.get("nsbpath") or ""
    cod = com_mod.get("code") or ""
    if not nsb or not cod:
        return None
    url = (f"{_sccf_base(host, slug)}{nsb}/"
           f"CM_T5_{MARKET_PL}{LANG_PL}{brand_code}_{cod}.json")
    try:
        r = scraper_utils.fetch_with_retry(session, url, retries=2, timeout=60)
        return r.json()
    except Exception as e:
        print(f"    ⚠ {cod}: nie pobrano cennika ({e})")
        return None


def versions_from_cm(cm_json):
    """Vehs[] -> lista wersji: kod MVSS, opis, trim, cena brutto."""
    out = []
    for veh in cm_json.get("Vehs") or []:
        prices = veh.get("PriceArray") or []
        brutto = to_brutto(prices[0]) if prices else 0
        if brutto <= 0:
            continue
        out.append({
            "mvss": veh.get("Cod") or "",
            "des": (veh.get("Des") or "").strip(),
            "trim": (veh.get("ComVersDes") or "").strip(),
            "price": brutto,
        })
    return out


def com_mod_name(cm_json, fallback=""):
    """Handlowa nazwa modelu (ComModDes), np. 'Avenger 100% Elektryczny'."""
    com = cm_json.get("ComMod") or {}
    return (com.get("ComModDes") or fallback or "").strip()


# --- Klasyfikacja z opisu wersji -------------------------------------------

def get_fuel(des, model_name=""):
    """Typ paliwa z opisu wersji (+ nazwy modelu). Kolejność testów ma
    znaczenie: 'e-Hybrid Plug-in' to PHEV, 'MHEV 4XE' zwykła hybryda,
    'BEV eMotor' elektryk — od najbardziej szczegółowego wzorca.

    Nazwa modelu jest potrzebna, bo Abarth opisuje elektryki wyłącznie
    nazwą ("Abarth 500e Turismo 155 KM" — ani BEV, ani kWh w opisie).
    """
    d = f"{des or ''} {model_name or ''}".upper()
    if "PLUG-IN" in d or "PLUG IN" in d or "PHEV" in d:
        return "Plug-in Hybrid"
    if "MHEV" in d or "HYBRID" in d or "HYBRYDA" in d or "IBRIDA" in d:
        return "Hybrid"
    if ("BEV" in d or "ELEKTRYCZN" in d or "EMOTOR" in d
            or "KWH" in d or "ELETTRICA" in d
            # 500e, 600e, e-500 — "e" przy numerze modelu oznacza elektryka
            or re.search(r"\b\d{3}\s?E\b", d)):
        return "Electric"
    if "JTD" in d or "DIESEL" in d or "MULTIJET" in d or "BLUEHDI" in d:
        return "Diesel"
    return "Gasoline"


def engine_desc(des, make_label, model_name, trim):
    """Opis wersji bez powtórzonej marki/modelu/trimu.

    'Abarth 500e Hatchback Turismo 155 KM' + model '500e Hatchback' + trim
    'Turismo' -> '155 KM'. Bez tego opis w feedzie brzmi jak zacinająca się
    płyta: "Nowy Abarth 500e Turismo · Abarth 500e Turismo 155 KM".
    """
    out = des or ""
    for part in [make_label, model_name, trim]:
        if not part:
            continue
        out = re.sub(re.escape(part), " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip(" -·,")
    return out or des or ""


def _strip_diacritics(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


STOPWORDS = {"nowy", "nowa", "nowe", "the", "100", "my25", "my26",
             "modele", "model", "pl"}

# Napęd tym samym słowem po polsku, angielsku i w żargonie technicznym —
# sprowadzamy do jednego tokenu, żeby "Grande Pande Electric" nie dopasowało
# się do strony "grande-panda-benzyna" (zdarzyło się przed tą normalizacją).
POWERTRAIN_SYNONYMS = [
    (r"plug[\s-]?in|phev", " phev "),
    (r"elektryczn\w*|electric\w*|elettrica|\bbev\b", " ev "),
    (r"hybryd\w*|hybrid\w*|\bmhev\b|ibrida", " hyb "),
    (r"benzyn\w*|gasoline|\bice\b", " gas "),
    (r"diesel|multijet|\bjtd\w*\b", " dsl "),
]
# wszystkie kanoniczne tokeny muszą mieć < 5 znaków, inaczej _stem
# utnie je ("petrol" -> "petr") i kontrola napędu przestanie działać
POWERTRAIN_TOKENS = {"phev", "ev", "hyb", "gas", "dsl"}


def _stem(token):
    """Skrót tokenu odporny na literówki i odmianę: 'pande'/'panda' -> 'pand',
    'elektryczny'/'elektryczna' -> 'elek'. Tokeny z cyfrą (500e, 4xe, 600)
    zostają w całości — to one odróżniają modele."""
    if any(ch.isdigit() for ch in token) or len(token) < 5:
        return token
    return token[:4]


def _tokens(text, drop=()):
    """Znormalizowane tokeny do dopasowywania nazw modeli do adresów stron."""
    t = _strip_diacritics((text or "").lower())
    t = t.replace("+", " plus ").replace("%", " ")
    for pattern, canonical in POWERTRAIN_SYNONYMS:
        t = re.sub(pattern, canonical, t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    skip = STOPWORDS | {_strip_diacritics(d.lower()) for d in drop}
    return {_stem(w) for w in t.split() if w and w not in skip}


# --- Strony modeli: link + zdjęcie + ewentualna rata ------------------------

def _absolute(host, url):
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return f"https://{host}{url if url.startswith('/') else '/' + url}"


def fetch_model_cards(session, host):
    """Karty "gama modeli" ze strony głównej marki: nazwa + link + zdjęcie.

    To jedyne wiarygodne źródło zdjęć — og:image stron modeli jest zepsute
    (fiat.pl podaje grafikę Lancii, jeep.pl sam adres domeny), a serwis
    renderów konfiguratora wymaga autoryzacji.
    """
    try:
        r = scraper_utils.fetch_with_retry(session, f"https://{host}/",
                                           retries=2, timeout=40)
    except Exception as e:
        print(f"  ⚠ Nie pobrano strony głównej {host}: {e}")
        return []

    cards = []
    soup = BeautifulSoup(r.text, "html.parser")
    for card in soup.select("[class*=ModelRangeCard]"):
        title_el = card.select_one("[class*=cardTitle]")
        link_el = card.find("a", href=True)
        img_el = card.find("img", src=True)
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title or not link_el:
            continue
        # tylko strony samej marki — karty Jeepa prowadzą na finansowanie.jeep.pl,
        # a to oferty abonamentowe, nie strony modeli
        if _absolute(host, link_el["href"]).split("/")[2] != host:
            continue
        cards.append({
            "text": title,
            "url": _absolute(host, link_el["href"]),
            "image": _absolute(host, img_el["src"]) if img_el else "",
        })
    return cards


def fetch_sitemap_pages(session, host, url_pattern):
    """Zapasowe źródło linków: adresy stron modeli z sitemapy (bez zdjęć)."""
    try:
        r = scraper_utils.fetch_with_retry(
            session, f"https://{host}/sitemap.xml", retries=2, timeout=40)
    except Exception as e:
        print(f"  ⚠ Brak sitemapy {host}: {e}")
        return []
    rx = re.compile(url_pattern)
    urls = sorted({loc for loc in re.findall(r"<loc>([^<]+)</loc>", r.text)
                   if rx.search(loc)})
    # tekstem jest CAŁA ścieżka, nie ostatni segment: Jeep zagnieżdża warianty
    # (/modele/avenger/e-hybrid), więc sam ostatni segment gubił nazwę modelu
    # i Compass e-Hybrid dopasowywał się do strony Avengera
    return [{"text": re.sub(r"^https?://[^/]+", "", u), "url": u, "image": ""}
            for u in urls]


def match_candidate(model_name, candidates, brand_words=()):
    """Najlepiej pasujący kandydat (karta lub adres z sitemapy) albo None.

    Kluczowa jest TRAFNOŚĆ kandydata, nie pokrycie nazwy modelu: strona
    "Qubo L" obsługuje modele "Qubo L 5-miejscowy" i "Qubo L 7-miejscowy",
    więc każdy jej token musi się znaleźć w nazwie modelu, ale nie odwrotnie.
    Przy równej trafności wygrywa kandydat bardziej szczegółowy (wyższe
    pokrycie nazwy) — dzięki temu "600 Hybrid" trafia na stronę 600 Hybrid,
    a nie na ogólną stronę 600.
    """
    want = _tokens(model_name, drop=brand_words)
    if not want:
        return None
    best, best_key = None, (0, 0.0, 0.0)
    for cand in candidates:
        have = _tokens(cand["text"], drop=brand_words)
        if not have:
            continue
        # Sprzeczny napęd dyskwalifikuje: elektryk nie może wskazywać na stronę
        # wersji benzynowej, choćby reszta nazwy pasowała idealnie. Napędu
        # szukamy też w adresie i zdjęciu kandydata — karta "NOWY AVENGER"
        # milczy o napędzie, ale jej zdjęcie to jawnie e-hybrid.
        cand_pt = ((have | _tokens(cand["url"]) | _tokens(cand["image"]))
                   & POWERTRAIN_TOKENS)
        want_pt = want & POWERTRAIN_TOKENS
        if want_pt and cand_pt and not (want_pt & cand_pt):
            continue
        common = want & have
        precision = len(common) / len(have)
        recall = len(common) / len(want)
        # PHEV przed zwykłą hybrydą: "Compass e-Hybrid Plug-In" pasuje i do
        # /nowy-compass/plug-in, i do /nowy-compass/hybrydowy — ma iść na plug-in
        if "phev" in want_pt and "phev" in cand_pt:
            pt_score = 2
        elif want_pt & cand_pt:
            pt_score = 1
        else:
            pt_score = 0
        key = (pt_score, precision, recall)
        if key > best_key:
            best, best_key = cand, key
    # sama trafność nie wystarczy: kandydat "600" pasuje idealnie do wszystkiego,
    # co zaczyna się od 600, więc wymagamy też realnego pokrycia nazwy modelu
    return best if best_key[1] >= 0.6 and best_key[2] > 0 else None


DAM_IMG_RX = re.compile(r"/content/dam/[A-Za-z0-9/_.-]+\.(?:jpg|jpeg|png|webp)",
                        re.IGNORECASE)
# elementy interfejsu, nie zdjęcia auta; "/wl/" to pasek gamy całej marki
# (widnieje na każdej stronie, więc podsuwał zdjęcia zupełnie innych modeli)
IMG_REJECT = ("logo", "icon", "popin", "pop-in", "header-menu", "whitelabel",
              "white-lable", "/wl/", "favicon", "footer", "menu", "badge",
              "social", "placeholder", "sprite")
# katalogi, w których marki trzymają zdjęcia modeli
IMG_PREFER = ("/models/", "model-range", "model-header", "gallery", "galeria")


def _pick_model_image(html_text, model_name=""):
    """Zdjęcie modelu ze strony marki (biblioteka DAM).

    Strony FCA nie mają użytecznego og:image (fiat.pl podaje grafikę Lancii,
    jeep.pl sam adres domeny), ale ładują zdjęcia z /content/dam/. Odsiewamy
    ikony i nawigację, a z reszty najwyżej punktujemy ścieżkę zawierającą
    nazwę modelu — inaczej strona 500 Hybrid potrafi oddać zdjęcie sąsiada
    z paska gamy.
    """
    want = {t for t in _tokens(model_name) if len(t) > 2}
    best, best_score = "", -1
    for path in DAM_IMG_RX.findall(html_text):
        low = path.lower()
        if any(bad in low for bad in IMG_REJECT):
            continue
        score = 0
        if want and any(tok in low for tok in want):
            score += 4
        if any(good in low for good in IMG_PREFER):
            score += 2
        if low.endswith((".jpg", ".jpeg", ".webp")):
            score += 1
        if score > best_score:
            best, best_score = path, score
    return best


def fetch_page_details(session, host, url, model_name=""):
    """(zdjęcie, rata) ze strony modelu — oba pola opcjonalne.

    Rata: dziś Fiat i Jeep podają na stronach modeli wyłącznie ceny
    gotówkowe, więc zwykle wychodzi None i wiersz idzie jako CASH, dokładnie
    jak w peugeot_model.py. Gdy wróci promocja, feed sam przełączy się na LEASE.
    """
    try:
        r = session.get(url, timeout=40)
        if r.status_code != 200:
            return "", None
    except Exception:
        return "", None

    # zdjęcia siedzą w zaescapowanym JSON-ie komponentów AEM
    image = _absolute(host, _pick_model_image(html_lib.unescape(r.text),
                                              model_name))

    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    return image, scraper_utils.extract_lease_price(text)


# --- Budowa wierszy feedu ---------------------------------------------------

def build_rows(make_label, id_prefix, model_name, version, page_url, image,
               lease, disclaimer):
    """Jedna wersja (MVSS) -> jeden wiersz feedu modelowego."""
    trim = version["trim"]
    des = version["des"]
    price = version["price"]

    full_title = f"{make_label} {model_name}".strip()
    if trim and trim.upper() not in model_name.upper():
        full_title = f"{full_title} {trim.title()}"
    engine = engine_desc(des, make_label, model_name, trim)

    if lease:
        offer_type, amount_price, amount_qualifier = "LEASE", f"{lease} PLN", "per month"
        tiktok_title = scraper_utils.format_model_title(full_title, f"{lease} PLN")
    else:
        offer_type, amount_price, amount_qualifier = "CASH", f"{price} PLN", "Total"
        tiktok_title = f"{full_title} · od {price} PLN"

    return {
        "vehicle_id": f"{id_prefix}-{version['mvss']}",
        "title": tiktok_title,
        "description": f"Nowy {full_title} · {engine} · Sprawdź ofertę!",
        "rodzaj": "modelowy",
        "make": make_label,
        "model": f"{make_label} {model_name}",
        "year": CURRENT_YEAR,
        "link": page_url,
        "image_link": image,
        "exterior_color": "Standard",
        "additional_image_link": "",
        "trim": trim,
        "offer_disclaimer": disclaimer,
        "offer_disclaimer_url": page_url,
        "price": f"{price} PLN",
        "offer_type": offer_type,
        "term_length": "",
        "offer_term_qualifier": "",
        "amount_price": amount_price,
        "amount_percentage": "",
        "amount_qualifier": amount_qualifier,
        "downpayment": "",
        "downpayment_qualifier": "",
        "emission_disclaimer": "",
        "emission_disclaimer_url": "",
        "emission_overlay_disclaimer": "",
        "emission_image_link": "",
        "fuel_type": get_fuel(des, model_name),
    }


def scrape_brand(brand):
    """Pełny feed modelowy jednej marki ex-FCA.

    brand: dict z kluczami host, slug, brand_code, make_label, id_prefix,
    page_pattern, fallback_link, disclaimer.
    """
    session = make_session()

    print(f"\n[1/3] Katalog modeli {brand['make_label']}...")
    scope = fetch_scope(session, brand["host"], brand["slug"], brand["brand_code"])
    com_mods = [c for c in (scope.get("comMods") or [])
                if (c.get("status") or "").lower() == "active"]
    print(f"  {len(com_mods)} aktywnych modeli handlowych")

    print("\n[2/3] Strony modeli (linki + zdjęcia)...")
    # karty gamy najpierw — mają zdjęcia; sitemapa to zapas na sam link
    cards = fetch_model_cards(session, brand["host"])
    sitemap = fetch_sitemap_pages(session, brand["host"], brand["page_pattern"])
    extra = brand.get("extra_pages") or []
    candidates = cards + extra + sitemap
    print(f"  {len(cards)} kart gamy + {len(extra)} ręcznych "
          f"+ {len(sitemap)} adresów z sitemapy")

    print("\n[3/3] Cenniki wersji...")
    rows = []
    page_cache = {}
    for com in com_mods:
        cm_json = fetch_com_mod(session, brand["host"], brand["slug"],
                                brand["brand_code"], com)
        if not cm_json:
            continue
        model_name = com_mod_name(cm_json, com.get("desc"))
        versions = versions_from_cm(cm_json)
        if not versions:
            print(f"  ⚠ {model_name}: brak wersji z ceną — pomijam")
            continue

        match = match_candidate(model_name, candidates,
                                brand_words=(brand["make_label"], brand["slug"]))
        link = match["url"] if match else brand["fallback_link"]
        # ta sama strona obsługuje kilka modeli (np. 500 Hybrid Cabrio/3+1),
        # ale zdjęcie dobieramy per model — stąd model w kluczu cache'u
        cache_key = (link, model_name)
        if cache_key not in page_cache:
            page_cache[cache_key] = fetch_page_details(
                session, brand["host"], link, model_name)
        page_image, lease = page_cache[cache_key]
        if not match:
            # link zbiorczy (np. jeep.pl/modele) pokazuje najniższą ratę całej
            # gamy, nie tego modelu — w feedzie byłaby nieprawdziwa (Avenger
            # dostawał 1422 zł z cudzej promocji), więc wiersz idzie jako CASH
            lease = None
        # zdjęcie z karty gamy jest wyselekcjonowane, ze strony — wywnioskowane
        image = (match["image"] if match and match["image"] else page_image)

        for version in versions:
            rows.append(build_rows(
                brand["make_label"], brand["id_prefix"], model_name, version,
                link, image, lease, brand["disclaimer"]))

        notes = []
        if not match:
            notes.append("link zbiorczy")
        if not image:
            notes.append("bez zdjęcia")
        suffix = f"  ({', '.join(notes)})" if notes else ""
        print(f"  ✅ {model_name}: {len(versions)} wersji{suffix}")

    # MVSS bywa powtórzony między modelami handlowymi (np. ten sam wariant
    # w dwóch grupach) — vehicle_id musi zostać unikalny.
    return list({r["vehicle_id"]: r for r in rows}.values())
