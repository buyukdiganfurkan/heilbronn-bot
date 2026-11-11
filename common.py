"""Ortak yardımcılar: Telegram gönderimi, state dosyası, çerez kabulü."""
import json
import os
import re
import datetime as dt
from pathlib import Path

import requests

STATE_DIR = Path(__file__).parent / "state"
TODAY = dt.date.today()


def _token(token_env):
    tok = os.environ.get(token_env) or os.environ.get("TELEGRAM_TOKEN")
    if not tok:
        raise SystemExit("TELEGRAM_TOKEN secret eksik")
    return tok.strip()


def _chat_id(token, token_env="TELEGRAM_TOKEN"):
    cid = os.environ.get("TELEGRAM_CHAT_ID")
    if cid:
        return cid
    base = f"https://api.telegram.org/bot{token}"
    saved = load_state("chat")
    # Bota en son mesaj atan sohbeti bul (Telegram bunu sadece 24 saat tutar)
    r = requests.get(f"{base}/getUpdates", timeout=30).json()
    for upd in reversed(r.get("result", [])):
        msg = upd.get("message") or upd.get("channel_post")
        if msg:
            saved[token_env] = msg["chat"]["id"]
            save_state("chat", saved)
            return msg["chat"]["id"]
    if saved.get(token_env):
        return saved[token_env]
    me = requests.get(f"{base}/getMe", timeout=30).json()
    if not me.get("ok"):
        raise SystemExit(f"TELEGRAM_TOKEN geçersiz (Telegram yanıtı: {me.get('description')}, "
                         f"token uzunluğu {len(token)}, boşluk var mı: {token != token.strip()}). "
                         "BotFather'daki tokenı tekrar kopyalayıp secret'ı güncelle.")
    raise SystemExit(f"Chat ID bulunamadı: Telegram'da @{me['result'].get('username')} botuna /start yaz, "
                     "sonra tekrar çalıştır.")


def send(text, photo=None, token_env="TELEGRAM_TOKEN"):
    token = _token(token_env)
    chat = _chat_id(token, token_env)
    base = f"https://api.telegram.org/bot{token}"
    if photo and Path(photo).exists():
        with open(photo, "rb") as f:
            requests.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": text[:1000]},
                          files={"photo": f}, timeout=60)
        if len(text) <= 1000:
            return
        text = text[1000:]
    for i in range(0, len(text), 4000):
        requests.post(f"{base}/sendMessage", data={
            "chat_id": chat, "text": text[i:i + 4000], "disable_web_page_preview": "true"}, timeout=30)


def load_state(name):
    p = STATE_DIR / f"{name}.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_state(name, data):
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))


COOKIE_RE = re.compile(r"(alle akzeptieren|akzeptieren|accept all|accept|zustimmen|einverstanden|allow all|alle zulassen|ok, verstanden)", re.I)


def accept_cookies(page):
    for frame in [page] + list(page.frames):
        try:
            btn = frame.get_by_role("button", name=COOKIE_RE)
            if btn.count():
                btn.first.click(timeout=2000)
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass


def warn_once_per_day(state, key, text, photo=None, token_env="TELEGRAM_TOKEN"):
    """Aynı hata uyarısını günde en fazla bir kez gönder."""
    today = TODAY.isoformat()
    if state.get(key) != today:
        send(text, photo=photo, token_env=token_env)
        state[key] = today


def is_debug():
    return os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
