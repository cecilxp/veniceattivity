#!/usr/bin/env python3
"""
Monitor annunci di cessione bar / ristoranti a Venezia centro storico (isola).
Controlla alcuni portali, filtra per zona e tipo di locale, e invia le novità
a un bot Telegram. Gli annunci già visti sono salvati in seen.json.

Variabili d'ambiente richieste:
  TELEGRAM_BOT_TOKEN   token del bot (da @BotFather)
  TELEGRAM_CHAT_ID     id della chat a cui mandare i messaggi
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
# curl_cffi imita l'impronta TLS di Chrome: con "requests" i portali rispondono 403.
from curl_cffi import requests

# ---------------------------------------------------------------------------
# CONFIGURAZIONE — modifica qui se vuoi aggiungere fonti o parole chiave
# ---------------------------------------------------------------------------

SOURCES = [
    # name, url, regex che riconosce il link di un annuncio,
    # zona_certa: la pagina è già limitata al Comune di Venezia?
    # tipo_certo: la pagina è già limitata a bar/ristorazione?
    {
        "name": "Casa.it – Ristorazione",
        "url": "https://www.casa.it/vendita/attivita-licenze-commerciali/venezia/ristorazione/",
        "link": r"^(https://www\.casa\.it)?/immobili/\d+/?$",
        "tipo_certo": True,
    },
    {
        "name": "Casa.it – Bar, pub e caffè",
        "url": "https://www.casa.it/vendita/attivita-licenze-commerciali/venezia/bar-pub-caffe/",
        "link": r"^(https://www\.casa\.it)?/immobili/\d+/?$",
        "tipo_certo": True,
    },
    {
        "name": "Immobiliare.it – Licenze",
        "url": "https://www.immobiliare.it/Venezia/licenze_in_vendita-Venezia.html",
        "link": r"^(https://www\.immobiliare\.it)?/annunci/\d+/?$",
        "tipo_certo": False,
        "generico_ok": True,  # titoli generici "Attività commerciale"
    },
    {
        "name": "Idealista – Cessione attività",
        "url": "https://www.idealista.it/cessione-attivita/venezia-venezia/con-vendita-attivita/",
        "link": r"^(https://www\.idealista\.it)?/immobile/\d+/?$",
        "tipo_certo": False,
        "generico_ok": True,
    },
    {
        "name": "Subito.it – bar",
        "url": "https://www.subito.it/annunci-veneto/vendita/uffici-locali-commerciali/venezia/venezia/?q=bar",
        "link": r"^(https://www\.subito\.it)?/uffici-locali-commerciali/.+-\d+\.htm$",
        "tipo_certo": False,
    },
    {
        "name": "Subito.it – ristorante",
        "url": "https://www.subito.it/annunci-veneto/vendita/uffici-locali-commerciali/venezia/venezia/?q=ristorante",
        "link": r"^(https://www\.subito\.it)?/uffici-locali-commerciali/.+-\d+\.htm$",
        "tipo_certo": False,
    },
    {
        "name": "Subito.it – cessione",
        "url": "https://www.subito.it/annunci-veneto/vendita/uffici-locali-commerciali/venezia/venezia/?q=cessione",
        "link": r"^(https://www\.subito\.it)?/uffici-locali-commerciali/.+-\d+\.htm$",
        "tipo_certo": False,
    },
]

# Zone dell'isola di Venezia (sestieri e toponimi frequenti negli annunci).
ZONE_ISOLA = [
    "san marco", "castello", "cannaregio", "dorsoduro", "san polo", "santa croce",
    "giudecca", "rialto", "strada nova", "strada nuova", "santi apostoli",
    "san canciano", "guglie", "san leonardo", "san geremia", "san barnaba",
    "santa margherita", "arsenale", "via garibaldi", "piazzale roma",
    "tronchetto", "san zaccaria", "san bartolomeo", "fondamenta", "campo ",
    "calle ", "sestiere", "centro storico", "zattere", "frari",
    "san giacomo", "misericordia", "ghetto", "santa lucia",
    "san trovaso", "san stae", "san vio", "sant'elena", "santa marta",
    "san pietro di castello", "bragora", "formosa", "rio terà", "rio tera",
    "salizada", "ruga ", "sacca fisola",
]

# Isole minori: metti True per includerle anche loro.
INCLUDI_ISOLE_MINORI = False
ISOLE_MINORI = ["lido", "murano", "burano", "pellestrina", "torcello", "sant'erasmo"]

# Se compare una di queste, l'annuncio NON è sull'isola.
ESCLUSE = [
    "mestre", "marghera", "favaro", "carpenedo", "chirignago", "zelarino",
    "campalto", "tessera", "dese", "gazzera", "trivignano", "malcontenta",
    "catene", "asseggiano", "bissuola", "terraglio", "cipressina", "altobello",
    "via piave", "corso del popolo", "via torino", "piazza ferretto",
    "erminio ferretto", "jesolo", "caorle", "eraclea", "mirano", "spinea",
    "dolo", "scorz*", "noale", "martellago", "mogliano", "chioggia", "sottomarina",
    "cavallino", "portogruaro", "camponogara", "quarto d'altino", "marcon",
    "san donà", "bibione", "mira ", "oriago", "stra ", "vigonovo", "treviso",
    "padova", "asta",  # le aste giudiziarie di solito non sono cessioni di attività
]

# Parole che indicano bar / ristorazione.
TIPO_LOCALE = [
    "bar", "ristorant*", "trattori*", "osteri*", "bacar*", "bàcaro", "pizzeri*",
    "pizza", "caffè", "caffe", "caffetteria", "pub", "enoteca", "wine",
    "gelateri*", "pasticceri*", "cicchett*", "tavola calda", "snack", "cocktail",
    "rosticceria", "bistrot", "somministrazione", "kebab", "paninoteca",
    "birreria", "locale con cucina", "ristorazione", "food", "take away",
    "street food", "piadineria", "cucina",
]

# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
SEEN_FILE = ROOT / "seen.json"

# User-Agent e gli altri header da browser li mette curl_cffi (impersonate="chrome").
HEADERS = {
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
}

PRICE_RE = re.compile(r"€\s?[\d\.]+(?:,\d+)?|[\d\.]{4,}(?:,\d+)?\s?€|trattativa riservata|prezzo su richiesta", re.I)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def canonical(url: str) -> str:
    return url.split("?")[0].split("#")[0].rstrip("/")


def card_text(a) -> str:
    """Risale dal link al contenitore dell'annuncio e ne restituisce il testo."""
    node = a
    best = clean(a.get_text(" "))
    href = canonical(a.get("href", ""))
    for _ in range(8):
        parent = node.parent
        if parent is None or parent.name in ("body", "html", "main"):
            break
        # Ci fermiamo se il contenitore include altri annunci.
        other = {canonical(x.get("href", "")) for x in parent.find_all("a", href=True)}
        other_listing = [o for o in other if o != href and re.search(r"\d{6,}", o)]
        if other_listing:
            break
        node = parent
        best = clean(node.get_text(" "))
        if len(best) > 1500:
            break
    return best[:1500]


def fetch_source(src: dict) -> list[dict]:
    r = requests.get(src["url"], headers=HEADERS, impersonate="chrome", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    pattern = re.compile(src["link"])
    found: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not pattern.search(href):
            continue
        url = canonical(urljoin(src["url"], href))
        text = card_text(a)
        heading = a.find(["h1", "h2", "h3", "h4"])
        title = clean(a.get("title") or (heading.get_text(" ") if heading else "") or a.get_text(" ")) or text[:90]
        prev = found.get(url)
        if prev is None or len(text) > len(prev["text"]):
            found[url] = {"url": url, "title": title[:150], "text": text, "source": src["name"]}
    if not found and len(r.text) < 20000:
        raise RuntimeError("pagina vuota o bloccata dal sito")
    return list(found.values())


def has_any(text: str, words: list[str]) -> str | None:
    """Cerca parole intere; una parola che finisce con * è una radice (es. ristorant*)."""
    for w in words:
        stem = w.endswith("*")
        core = w.rstrip("*")
        pat = r"(?<![a-zà-ù])" + re.escape(core)
        if not stem and core[-1].isalpha():
            pat += r"(?![a-zà-ù])"
        if re.search(pat, text):
            return core
    return None


def classify(item: dict, tipo_certo: bool, generico_ok: bool = False) -> dict | None:
    t = (item["title"] + " " + item["text"]).lower()

    if has_any(t, ESCLUSE):
        return None
    zona = has_any(t, ZONE_ISOLA)
    isola_minore = has_any(t, ISOLE_MINORI)
    if isola_minore and not zona and not INCLUDI_ISOLE_MINORI:
        return None
    if not zona and not isola_minore:
        # Le pagine di Immobiliare coprono tutta la provincia: senza zona, scarto.
        if "immobiliare.it" in item["url"]:
            return None
        item["zona"] = "da verificare"
    else:
        item["zona"] = (zona or isola_minore).strip().title()

    if tipo_certo or has_any(t, TIPO_LOCALE):
        item["tipo_ok"] = True
    elif generico_ok:
        item["tipo_ok"] = False  # attività generica: la mandiamo ma segnalata
    else:
        return None

    m = PRICE_RE.search(item["text"])
    item["prezzo"] = clean(m.group(0)) if m else "n.d."
    return item


def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_item(it: dict) -> str:
    extra = "" if it["tipo_ok"] else "\n⚠️ tipo di attività non specificato"
    zona = "❓ zona da verificare" if it["zona"] == "da verificare" else f"📍 {html_escape(it['zona'])}"
    return (
        f"<b>{html_escape(it['title'])}</b>\n"
        f"💶 {html_escape(it['prezzo'])}   {zona}{extra}\n"
        f"🔎 {html_escape(it['source'])}\n"
        f"{it['url']}"
    )


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("---- (Telegram non configurato, stampo il messaggio) ----\n" + text)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "true"},
        timeout=30,
    )
    if r.status_code != 200:
        # Fermiamo il giro senza salvare seen.json: così gli annunci non vanno persi
        # e il workflow risulta fallito (rosso) nella scheda Actions.
        sys.exit(f"Errore Telegram: {r.status_code} {r.text}")
    time.sleep(1.1)  # rispetta i limiti di Telegram


def send_batched(header: str, blocks: list[str]) -> None:
    msg = header
    for b in blocks:
        if len(msg) + len(b) + 2 > 3900:
            send_telegram(msg)
            msg = ""
        msg += ("\n\n" if msg else "") + b
    if msg:
        send_telegram(msg)


def main() -> int:
    seen = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {}
    first_run = not any(not k.startswith("_") for k in seen)

    results: dict[str, dict] = {}
    errors = []
    for src in SOURCES:
        try:
            items = fetch_source(src)
            print(f"{src['name']}: {len(items)} annunci letti")
            for it in items:
                c = classify(it, src.get("tipo_certo", False), src.get("generico_ok", False))
                if c and c["url"] not in results:
                    results[c["url"]] = c
        except Exception as e:  # un sito che blocca non deve fermare gli altri
            errors.append(f"{src['name']}: {e}")
            print(f"ERRORE {src['name']}: {e}", file=sys.stderr)
        time.sleep(2)

    new = [it for url, it in results.items() if url not in seen]
    print(f"Annunci pertinenti: {len(results)}, nuovi: {len(new)}")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if new:
        header = (
            f"🍷 <b>Annunci attualmente online</b> — bar e ristoranti a Venezia isola ({len(new)})"
            if first_run else
            f"🆕 <b>{len(new)} nuov{'o annuncio' if len(new) == 1 else 'i annunci'}</b> — bar e ristoranti a Venezia isola"
        )
        send_batched(header, [format_item(it) for it in new])
    elif first_run:
        send_telegram("✅ Monitor attivo: al momento nessun annuncio trovato. Ti scrivo appena ne esce uno.")

    # Avviso "nessun sito raggiungibile" al massimo una volta al giorno.
    if len(errors) == len(SOURCES) and seen.get("_avviso_errori") != now[:10]:
        seen["_avviso_errori"] = now[:10]
        send_telegram("⚠️ Monitor annunci: nessun sito è stato raggiungibile in questo giro.\n" +
                      html_escape("\n".join(errors)))

    for it in new:
        seen[it["url"]] = {"title": it["title"], "first_seen": now}
    # Un piccolo commit al giorno evita che GitHub sospenda il workflow per inattività.
    seen["_ultimo_controllo"] = now[:10]
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
