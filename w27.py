"""W27 (apartments-hn.de) boş daire takibi.

Sayfadaki daire tablosunu gerçek tarayıcıyla okur. "Jetzt bewerben" linki olan
(yani başvurulabilir) her daire için, daha önce bildirilmediyse Telegram'a yazar.
"""
import traceback

from playwright.sync_api import sync_playwright

from common import send, load_state, save_state, warn_once_per_day, is_debug

URL = "https://www.apartments-hn.de/apartment-mieten"
ROW = "tr.book-property__table-row"
TOKEN_ENV = "TELEGRAM_TOKEN"

JS = """
rows => rows.map(r => {
  const link = r.querySelector('a[href]');
  const tds = [...r.querySelectorAll('td')].map(td => td.innerText.replace(/\\s+/g, ' ').trim());
  return {tds, href: link ? link.href : null, label: link ? link.innerText.trim() : ''};
})
"""


def read_table():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="de-DE", viewport={"width": 1400, "height": 2000})
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(ROW, timeout=60000)
        page.wait_for_timeout(3000)
        rows = page.eval_on_selector_all(ROW, JS)
        browser.close()
    return rows


def fmt(a):
    star = "⭐ " if "partner" in a["type"].lower() else ""
    return (f"{star}{a['no']} | {a['type']} | {a['loc']} | {a['size']} m² | {a['rent']} € | "
            f"{a['avail']}\n{a['href']}")


def main():
    state = load_state("w27")
    known = state.get("known", {})
    if not isinstance(known, dict):
        known = {}
    first_run = not state.get("initialized")

    try:
        rows = read_table()
        if len(rows) < 20:
            raise ValueError(f"tablo eksik okundu ({len(rows)} satır)")
    except Exception as e:
        traceback.print_exc()
        state["fail_streak"] = state.get("fail_streak", 0) + 1
        if state["fail_streak"] >= 3 or is_debug():
            warn_once_per_day(state, "last_warn" if not is_debug() else "dbg",
                              f"W27 sayfası okunamıyor ({state['fail_streak']} kez), elle bak:\n{URL}\n{e}",
                              token_env=TOKEN_ENV)
        save_state("w27", state)
        return

    free = {}
    for r in rows:
        if not r["href"] or len(r["tds"]) < 6:
            continue
        t = r["tds"]
        free[t[0]] = {"no": t[0], "type": t[1], "loc": t[2], "size": t[3], "rent": t[4],
                      "avail": t[5].replace(r["label"], "").strip(), "href": r["href"]}
    print(f"{len(rows)} satır, {len(free)} başvurulabilir:", sorted(free))

    new = [a for no, a in free.items() if no not in known]
    if first_run or is_debug():
        head = "W27 botu çalışıyor. Şu an başvurulabilir daireler" if free else \
            "W27 botu çalışıyor. Şu an başvurulabilir daire yok, çıkınca yazacağım."
        body = "\n\n".join(fmt(a) for a in free.values())
        send(f"{head} ({len(free)}):\n\n{body}\n\n⭐ = partner dairesi\n{URL}" if free else head,
             token_env=TOKEN_ENV)
    elif new:
        send(f"🏠 W27'de YENİ daire açıldı ({len(new)}):\n\n" + "\n\n".join(fmt(a) for a in new)
             + f"\n\n⭐ = partner dairesi. Hemen başvur:\n{URL}", token_env=TOKEN_ENV)

    state["fail_streak"] = 0
    state["initialized"] = True
    # Listeden düşen daireyi unut: tekrar açılırsa yine haber ver
    state["known"] = {no: a["avail"] for no, a in free.items()}
    save_state("w27", state)


if __name__ == "__main__":
    main()
