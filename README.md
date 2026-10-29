# bfep-autopost

Автопубликация в Telegram-канал t.me/bestfuneveningapp через бота @bestfuneveningapp_bot.

- `schedule.json` — расписание (время в UTC; Дубай = UTC+4), подпись и файл.
- `posted.json` — что уже опубликовано (пишет робот).
- Робот (`.github/workflows/autopost.yml`) запускается каждые 10 минут и публикует всё, чему пора.
- Секрет `TG_BOT_TOKEN` — токен бота (Settings → Secrets and variables → Actions).
- `media/` — ролики с простыми именами: `R089-ru.mp4`, `R089-en.mp4` (v1.2 с фразой-проблемой), `R012-ru-v1.1.mp4` (исходные версии). Публичная ссылка для Metricool: `https://raw.githubusercontent.com/bfepspace/bfep-autopost/main/media/<файл>`.
