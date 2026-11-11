"""Heilbronn Ausländerbehörde erken randevu takibi.

Randevu sitesinin (eTermin) kendi takvim servisine sorar: "Erteilung
Aufenthaltserlaubnis" için bugünden itibaren ilk boş günler hangileri?
Mevcut randevudan (CURRENT_APPOINTMENT) daha erken bir gün çıkınca Telegram'a yazar.
"""
import os
import datetime as dt

import requests

from common import send, load_state, save_state, warn_once_per_day, is_debug, TODAY

WEBID = "qtermin-stadtheilbronn-abh"
BOOK_URL = f"https://www.etermin.net/{WEBID}"
# 144511 = Erteilung Aufenthaltserlaubnis (ilk oturum izni), 20 dk
SERVICE_ID = os.environ.get("SERVICE_ID") or "144511"
DURATION = os.environ.get("SERVICE_DURATION") or "20"
CURRENT = dt.date.fromisoformat(os.environ.get("CURRENT_APPOINTMENT") or "2027-04-08")
TOKEN_ENV = "TERMIN_TELEGRAM_TOKEN"   # yoksa TELEGRAM_TOKEN kullanılır


def free_days():
    params = {
        "date": TODAY.isoformat(), "serviceid": SERVICE_ID, "rangesearch": "1",
        "caching": "false", "capacity": "1", "duration": DURATION, "cluster": "false",
        "slottype": "0", "fillcalendarstrategy": "0", "showavcap": "false",
        "appfuture": "270", "appdeadline": "480", "appdeadlinewm": "1",
        "oneoff": "null", "msdcm": "0", "calendarid": "",
    }
    r = requests.get("https://www.etermin.net/api/timeslots", params=params, timeout=40, headers={
        "webid": WEBID, "Accept": "application/json", "Referer": BOOK_URL,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"})
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError(f"beklenmeyen yanıt: {r.text[:200]}")
    days = set()
    for x in data:
        if x.get("available") and x.get("start"):
            days.add(dt.date.fromisoformat(x["start"][:10]))
    return sorted(days)


def main():
    state = load_state("termin")
    try:
        days = free_days()
    except Exception as e:
        state["fail_streak"] = state.get("fail_streak", 0) + 1
        print("HATA:", e)
        if state["fail_streak"] >= 6 or is_debug():
            warn_once_per_day(state, "last_warn" if not is_debug() else "dbg",
                              f"Randevu botu siteyi okuyamıyor ({state['fail_streak']} kez): {e}\n{BOOK_URL}",
                              token_env=TOKEN_ENV)
        save_state("termin", state)
        return

    state["fail_streak"] = 0
    earliest = days[0] if days else None
    state["last_earliest"] = earliest.isoformat() if earliest else None
    print("boş günler:", days)

    if is_debug():
        send(f"[TEST] Randevu botu çalışıyor.\nŞu anki randevun: {CURRENT:%d.%m.%Y}\n"
             f"Sitede en erken boş gün: {earliest:%d.%m.%Y}\n" if earliest else
             "[TEST] Randevu botu çalışıyor ama sitede şu an hiç boş gün görünmüyor.",
             token_env=TOKEN_ENV)

    earlier = [d for d in days if d < CURRENT]
    if earlier and state.get("notified") != earlier[0].isoformat():
        send(f"📅 DAHA ERKEN RANDEVU VAR!\nEn erken: {earlier[0]:%d.%m.%Y} "
             f"(şu anki randevun {CURRENT:%d.%m.%Y})\n"
             f"Erken günler: {', '.join(d.strftime('%d.%m.%Y') for d in earlier[:8])}\n\n"
             f"Hemen al: {BOOK_URL}\nHizmet: Aufenthaltserlaubnis > Erteilung Aufenthaltserlaubnis\n\n"
             f"Yeni randevuyu aldıktan sonra eskisini iptal et "
             f"(aynı işlem için iki randevu olursa ikisi de iptal edilebiliyor).",
             token_env=TOKEN_ENV)
        state["notified"] = earlier[0].isoformat()
    elif not earlier:
        state.pop("notified", None)

    save_state("termin", state)


if __name__ == "__main__":
    main()
