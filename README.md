# Heilbronn botları

İki bot, GitHub Actions üzerinde ücretsiz çalışır ve Telegram'a mesaj atar:

- **w27.py**: W27 (apartments-hn.de) sayfasında yeni boş daire veya başvuru linki çıkınca haber verir. 06:00-23:00 arası her 20 dk.
- **termin.py**: Stadt Heilbronn Ausländerbehörde (qtermin) sayfasında mevcut randevundan daha erken bir gün çıkınca haber verir. 06:00-22:00 arası her 10 dk.

## Ayarlar (Settings → Secrets and variables → Actions)

Secrets:
- `TELEGRAM_TOKEN`: BotFather'ın verdiği token
- `TELEGRAM_CHAT_ID`: (isteğe bağlı) boş bırakırsan bota en son mesaj atan sohbet kullanılır
- `TERMIN_TELEGRAM_TOKEN`: (isteğe bağlı) randevu botu için ayrı bir Telegram botu kullanacaksan

Variables:
- `CURRENT_APPOINTMENT`: mevcut randevu tarihi, örn. `2027-04-08`
- `SERVICE_TEXT`: qtermin'de seçilecek hizmetin adındaki bir kelime, örn. `Studium`

## Test

Actions sekmesi → workflow'u seç → **Run workflow** → `debug` kutusunu işaretle.
Telegram'a ekran görüntüsü ve sayfa metni gelir; doğru sayfaya ulaşıp ulaşmadığını oradan görürsün.
