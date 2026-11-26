"""Heilbronn ogrenci yurdu / apartman siteleri -> Telegram.
W27 disindaki siteleri tarar. Her sitede "bos yer" ile ilgili satirlari okur,
bir onceki calistirmaya gore YENI cikan satirlari Telegram'a atar."""
import hashlib
import re

from playwright.sync_api import sync_playwright

from common import send, load_state, save_state, accept_cookies, warn_once_per_day

SITES = {
    "Rosenberg (ogrenci odalari)": "https://rosenberg-quartier.de/en/apartments/student-rooms",
    "Rosenberg (daireler)": "https://rosenberg-quartier.de/en/apartments/non-serviced-apartments",
    "studenten.hn / GEWO": "https://studenten.hn/freie-appartements",
    "i Live Urban Living": "https://urban-living-heilbronn.de",
    "i Live Campus Living": "https://campus-living-heilbronn.de",
    "PUROpartment": "https://puropartment.de/mieten",
    "THE PLAZE": "https://theplaze.de",
    "Lohtor": "https://studentinheilbronn.de/apartments.html",
    "Stay4Job": "https://stay4job.de",
    "Meine Studibude": "https://meine-studibude.de",
    "Wohnraum Heilbronn": "https://wohnraum-heilbronn.de",
    "TUM Living": "https://living.tum.de/listings?viewMode=list&tumLocation=HEILBRONN",
}

# Bos yerle ilgili olabilecek satirlar
KEEP = re.compile(r"frei|verf[uü]gbar|available|vacan|ab sofort|einzug|move.?in|apartment|appartement|"
                  r"zimmer|room|studio|wohnung|m²|m2|qm|€|eur|miete|rent|vermietet|belegt|"
                  r"warteliste|waiting|keine|no .*available", re.I)
# Her calistirmada degisen, onemsiz satirlar
NOISE = re.compile(r"cookie|datenschutz|privacy|impressum|newsletter|copyright|©|login|anmelden$", re.I)


def norm(line):
    return re.sub(r"\s+", " ", line).strip()


def read_site(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    accept_cookies(page)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(4000)
    # "Load more / Mehr laden" butonlarina birkac kez bas
    for _ in range(6):
        try:
            btn = page.get_by_role("button", name=re.compile(r"load more|mehr laden|mehr anzeigen|show more", re.I))
            if not btn.count():
                break
            btn.first.click(timeout=3000)
            page.wait_for_timeout(2000)
        except Exception:
            break
    text = page.inner_text("body")
    lines = [norm(l) for l in text.splitlines()]
    lines = [l for l in lines if 3 <= len(l) <= 200 and KEEP.search(l) and not NOISE.search(l)]
    return list(dict.fromkeys(lines)), len(text)


def main():
    state = load_state("evler")
    sites_state = state.setdefault("sites", {})
    first_run = not sites_state
    unreadable, news, ok = [], [], 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="de-DE", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"))
        page = ctx.new_page()
        for name, url in SITES.items():
            try:
                lines, size = read_site(page, url)
            except Exception as e:
                print(f"{name}: hata {e}")
                unreadable.append(name)
                continue
            if size < 300 or not lines:
                # Sayfa bos ya da sadece JS kabugu geldi
                unreadable.append(name)
                continue
            ok += 1
            old = set(sites_state.get(name, {}).get("lines", []))
            new_lines = [l for l in lines if l not in old]
            sites_state[name] = {"lines": lines, "hash": hashlib.md5("\n".join(lines).encode()).hexdigest()}
            print(f"{name}: {len(lines)} satir, {len(new_lines)} yeni")
            if old and new_lines:
                news.append((name, url, new_lines))
        browser.close()

    if first_run:
        send(f"Ev takibi basladi. {ok} site okundu"
             + (f", okunamayan: {', '.join(unreadable)}" if unreadable else "")
             + ". Bundan sonra sadece degisiklikler gelecek.")
    else:
        for name, url, new_lines in news:
            body = "\n".join(f"- {l}" for l in new_lines[:15])
            send(f"🏠 {name}: sayfada yeni bilgi var\n\n{body}\n\nKontrol et: {url}")
        if unreadable:
            warn_once_per_day(state, "unreadable_warned",
                              "Ev takibi: bugun okunamayan siteler: " + ", ".join(unreadable))

    save_state("evler", state)


if __name__ == "__main__":
    main()
