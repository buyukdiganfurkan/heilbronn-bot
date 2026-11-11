"""Heilbronn Ausländerbehörde (qtermin) erken randevu takibi.

Randevu sayfasını açar, seçili hizmeti (SERVICE_TEXT) seçer, ileri butonlarına
basar ve takvimde görünen en erken tarihi bulur. Mevcut randevudan
(CURRENT_APPOINTMENT) daha erken bir tarih çıkınca Telegram'a mesaj atar.
"""
import os
import re
import datetime as dt
import traceback

from playwright.sync_api import sync_playwright

from common import send, load_state, save_state, accept_cookies, warn_once_per_day, is_debug, TODAY

URL = os.environ.get("TERMIN_URL") or "https://www.qtermin.de/qtermin-stadtheilbronn-abh"
SERVICE_TEXT = os.environ.get("SERVICE_TEXT") or "Studium"
CURRENT = dt.date.fromisoformat(os.environ.get("CURRENT_APPOINTMENT") or "2027-04-08")
TOKEN_ENV = "TERMIN_TELEGRAM_TOKEN"   # yoksa TELEGRAM_TOKEN kullanılır

NEXT_RE = re.compile(r"^\s*(weiter|next|termin suchen|termine suchen|freie termine|ok|bestätigen|übernehmen|verstanden)\s*$", re.I)
DE_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d\d)\b")
ISO_DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
     "september", "oktober", "november", "dezember"])}
LONG_DATE = re.compile(r"\b(\d{1,2})\.\s*(" + "|".join(MONTHS) + r")\s+(20\d\d)", re.I)
SLOT_URL = re.compile(r"(slot|free|frei|avail|termin|day|date|calendar|kalender)", re.I)


def dates_in(text, iso=True):
    out = set()
    for d, m, y in DE_DATE.findall(text):
        out.add((int(y), int(m), int(d)))
    for d, mon, y in LONG_DATE.findall(text):
        out.add((int(y), MONTHS[mon.lower()], int(d)))
    if iso:
        for y, m, d in ISO_DATE.findall(text):
            out.add((int(y), int(m), int(d)))
    res = set()
    for y, m, d in out:
        try:
            date = dt.date(y, m, d)
        except ValueError:
            continue
        if TODAY < date < CURRENT + dt.timedelta(days=400):
            res.add(date)
    return res


def select_service(page):
    """Hizmeti seç: satırdaki checkbox / + butonu / satırın kendisi."""
    pat = re.compile(SERVICE_TEXT, re.I)
    loc = page.get_by_text(pat)
    if not loc.count():
        return False
    target = loc.first
    target.scroll_into_view_if_needed()
    # Satır içinde checkbox, sayı kutusu veya + butonu ara
    for sel in ["xpath=ancestor::*[.//input[@type='checkbox']][1]//input[@type='checkbox']",
                "xpath=ancestor::*[.//button[normalize-space()='+']][1]//button[normalize-space()='+']",
                "xpath=ancestor::*[.//input[@type='number']][1]//input[@type='number']"]:
        try:
            el = target.locator(sel).first
            if el.count():
                if "number" in sel:
                    el.fill("1")
                else:
                    el.click(timeout=3000)
                return True
        except Exception:
            pass
    target.click(timeout=3000)
    return True


def click_next(page):
    for role in ("button", "link"):
        btns = page.get_by_role(role, name=NEXT_RE)
        for i in range(btns.count()):
            b = btns.nth(i)
            try:
                if b.is_visible() and b.is_enabled():
                    b.click(timeout=3000)
                    page.wait_for_timeout(2500)
                    return True
            except Exception:
                pass
    return False


def main():
    state = load_state("termin")
    json_dates = set()

    def on_response(resp):
        try:
            if SLOT_URL.search(resp.url) and "json" in (resp.headers.get("content-type") or ""):
                json_dates.update(dates_in(resp.text()))
        except Exception:
            pass

    shot = "termin.png"
    log = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(locale="de-DE", viewport={"width": 1400, "height": 2200})
            page.on("response", on_response)
            page.goto(URL, wait_until="networkidle", timeout=60000)
            accept_cookies(page)
            page.wait_for_timeout(3000)
            log.append(f"hizmet seçildi: {select_service(page)}")
            page.wait_for_timeout(1500)
            for _ in range(5):
                if not click_next(page):
                    break
                log.append("ileri")
                page.wait_for_load_state("networkidle")
            page.wait_for_timeout(4000)
            text = page.inner_text("body")
            page.screenshot(path=shot, full_page=True)
            browser.close()
    except Exception as e:
        traceback.print_exc()
        state["fail_streak"] = state.get("fail_streak", 0) + 1
        if state["fail_streak"] >= 3:
            warn_once_per_day(state, "last_warn", f"Termin botu 3 kez üst üste hata verdi: {e}\n{URL}",
                              photo=shot, token_env=TOKEN_ENV)
        save_state("termin", state)
        return

    page_dates = dates_in(text, iso=False)
    dates = sorted(page_dates | json_dates)
    earliest = dates[0] if dates else None

    if is_debug():
        send(f"[DEBUG TERMİN] hizmet='{SERVICE_TEXT}', mevcut randevu={CURRENT}\n"
             f"Adımlar: {', '.join(log)}\nSayfadaki tarihler: {sorted(page_dates)[:10]}\n"
             f"API tarihleri: {sorted(json_dates)[:10]}\n\n--- Sayfa metni ---\n{text[:3000]}",
             photo=shot, token_env=TOKEN_ENV)

    if not dates:
        state["empty_streak"] = state.get("empty_streak", 0) + 1
        # Hiç tarih okunamıyorsa akış bozulmuş olabilir: günde bir kez haber ver
        if state["empty_streak"] >= 12:
            warn_once_per_day(state, "last_warn",
                              "Termin botu uzun süredir hiç tarih okuyamadı (ya hiç yer yok ya da sayfa değişti). "
                              "Ekran görüntüsü ekte.", photo=shot, token_env=TOKEN_ENV)
    else:
        state["empty_streak"] = 0

    state["fail_streak"] = 0
    state["last_earliest"] = earliest.isoformat() if earliest else None

    if earliest and earliest < CURRENT and state.get("notified") != earliest.isoformat():
        others = ", ".join([d.strftime("%d.%m.%Y") for d in dates if d < CURRENT][:8])
        send(f"📅 DAHA ERKEN RANDEVU VAR!\nEn erken: {earliest:%d.%m.%Y} "
             f"(şu anki randevun {CURRENT:%d.%m.%Y})\nDiğer erken günler: {others}\n\n"
             f"Hemen al: {URL}\n\nYeni randevuyu aldıktan sonra eskisini iptal et "
             f"(aynı işlem için iki randevu olursa ikisi de iptal edilebiliyor).",
             photo=shot, token_env=TOKEN_ENV)
        state["notified"] = earliest.isoformat()
    elif not earliest or earliest >= CURRENT:
        state.pop("notified", None)

    save_state("termin", state)


if __name__ == "__main__":
    main()
