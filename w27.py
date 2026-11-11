"""W27 (apartments-hn.de) boş daire takibi.

Sayfayı gerçek tarayıcıyla açar (JavaScript ile yüklenen liste dahil), boş daire
işaretlerini ve başvuru linklerini toplar. Daha önce görülmemiş bir öğe çıkınca
Telegram'a ekran görüntüsüyle mesaj atar.
"""
import re
import traceback

from playwright.sync_api import sync_playwright

from common import send, load_state, save_state, accept_cookies, warn_once_per_day, is_debug

URLS = [
    "https://www.apartments-hn.de/apartment-mieten",
    "https://www.apartments-hn.de/en/book-apartment",
]
TOKEN_ENV = "TELEGRAM_TOKEN"

# Boşluk işaretleri
FREE_RE = re.compile(r"\b(frei|verfügbar|available|vacant|bald verfügbar|soon available|ab sofort)\b", re.I)
# "nicht verfügbar", "keine freien" gibi olumsuzlar
NEG_RE = re.compile(r"(nicht\s+(frei|verfügbar|available)|not\s+available|keine\s+(freien|verfügbaren|einheiten)|no\s+(free|vacant|units)|belegt|occupied|vermietet|rented)", re.I)
# Başvuru linki işaretleri
LINK_RE = re.compile(r"(reos|bewerb|apply|anfrage|request|buchen|book|reserv)", re.I)
# Sitenin her sayfada olan genel menü linklerini ele
GENERIC_HREF = re.compile(r"(apartments-hn\.de/?(en/?)?(book-apartment|apartment-mieten)?/?$|#|mailto:|tel:)", re.I)


def scan(page, url):
    json_hits = []

    def on_response(resp):
        try:
            if "json" in (resp.headers.get("content-type") or ""):
                body = resp.text()
                if FREE_RE.search(body):
                    json_hits.append(resp.url)
        except Exception:
            pass

    page.on("response", on_response)
    page.goto(url, wait_until="networkidle", timeout=60000)
    accept_cookies(page)
    page.wait_for_timeout(5000)
    # Lazy-load için aşağı kaydır
    for _ in range(6):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(700)

    texts = []
    for frame in page.frames:
        try:
            texts.append(frame.inner_text("body", timeout=5000))
        except Exception:
            pass
    text = "\n".join(texts)

    items = set()
    for line in text.splitlines():
        line = " ".join(line.split())
        if 3 < len(line) < 200 and FREE_RE.search(line) and not NEG_RE.search(line):
            items.add(f"satır: {line}")

    for frame in page.frames:
        try:
            links = frame.eval_on_selector_all(
                "a[href]", "els => els.map(e => [e.href, (e.innerText||'').trim()])")
        except Exception:
            continue
        for href, label in links:
            if LINK_RE.search(href + " " + label) and not GENERIC_HREF.search(href):
                items.add(f"link: {label[:60]} -> {href}")

    for u in json_hits:
        items.add(f"veri: {u}")
    page.remove_listener("response", on_response)
    return text, items


def main():
    state = load_state("w27")
    known = set(state.get("known", []))
    first_run = not state.get("initialized")
    new_items, all_items, errors, shot = [], set(), [], None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="de-DE", viewport={"width": 1400, "height": 2400})
        for i, url in enumerate(URLS):
            try:
                text, items = scan(page, url)
                all_items |= items
                fresh = sorted(items - known)
                if fresh or is_debug():
                    shot = f"w27_{i}.png"
                    page.screenshot(path=shot, full_page=True)
                    if is_debug():
                        send(f"[DEBUG W27] {url}\nBulunan öğe: {len(items)}\n\n"
                             + "\n".join(sorted(items))[:2500]
                             + "\n\n--- Sayfa metni ---\n" + text[:2500], photo=shot, token_env=TOKEN_ENV)
                new_items += [f"{x}  ({url})" for x in fresh]
            except Exception as e:
                errors.append(f"{url}: {e.__class__.__name__}: {str(e)[:200]}")
                traceback.print_exc()
        browser.close()

    if new_items:
        head = ("W27 bot çalışmaya başladı. Şu an sayfada görünenler:" if first_run
                else "🏠 W27'de YENİ hareket var! Hemen bak ve başvur:")
        msg = head + "\n\n" + "\n".join(new_items[:40]) + \
            "\n\nhttps://www.apartments-hn.de/apartment-mieten"
        send(msg, photo=shot, token_env=TOKEN_ENV)
    elif first_run:
        send("W27 bot çalışmaya başladı. Şu an boş daire işareti yok, çıkınca haber vereceğim.",
             token_env=TOKEN_ENV)

    if errors and len(errors) == len(URLS):
        state["fail_streak"] = state.get("fail_streak", 0) + 1
        if state["fail_streak"] >= 3:
            warn_once_per_day(state, "last_warn", "W27 sayfası 3 kez üst üste açılamadı, elle kontrol et:\n"
                              "https://www.apartments-hn.de/apartment-mieten\n\n" + "\n".join(errors),
                              token_env=TOKEN_ENV)
    else:
        state["fail_streak"] = 0
        # Kaybolan öğeleri unut, tekrar çıkarlarsa yine haber ver
        state["known"] = sorted(all_items)
        state["initialized"] = True

    save_state("w27", state)


if __name__ == "__main__":
    main()
