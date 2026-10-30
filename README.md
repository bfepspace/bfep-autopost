# bfep-autopost

Автопубликация в Telegram-канал t.me/bestfuneveningapp через бота @bestfuneveningapp_bot.

- `schedule.json` — расписание (время в UTC; Дубай = UTC+4), подпись и файл.
- `posted.json` — что уже опубликовано (пишет робот).
- Робот (`.github/workflows/autopost.yml`) запускается каждые 10 минут и публикует всё, чему пора.
- Секрет `TG_BOT_TOKEN` — токен бота (Settings → Secrets and variables → Actions).
- `media/` — ролики с простыми именами: `R089-ru.mp4`, `R089-en.mp4` (v1.2 с фразой-проблемой), `R012-ru-v1.1.mp4` (исходные версии). Публичная ссылка для Metricool: `https://raw.githubusercontent.com/bfepspace/bfep-autopost/main/media/<файл>`.
- `config.json` — переключатели: `buttons` (кнопки «Сыграть» и «Отправить другу» под постами), `interactive` (бот отвечает в чате), `first_comments` и `riddles` (тексты бота).
- `bot.py` — бот в чате канала: первый комментарий под постом, загадка дня с очками, /dice, /wheel, /who, /top, /invite (личные ссылки-приглашения). Между публикациями слушает Telegram; состояние — `bot_state.json`.
- В `schedule.json` можно ставить опросы: `"type": "poll", "question": …, "options": […]`, для викторины ещё `"correct"` (номер ответа с 0) и `"explanation"`.
- `"to": "chat"` — пост идёт в чат обсуждения канала (квиз-вечер). `"quiz": "<дата>"` у опроса — бот считает верные ответы; `"type": "quiz_results"` публикует итоги (`{top}` в подписи).
- `stats.json` — число подписчиков канала и чата, раз в день по Дубаю.
