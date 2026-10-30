"""Публикует в Telegram-канал всё, чему по schedule.json уже пора (бот: секрет TG_BOT_TOKEN)."""
import datetime, json, os, subprocess, sys

CHAT = os.environ.get("TG_CHAT", "@bestfuneveningapp")
TOKEN = os.environ.get("TG_BOT_TOKEN", "")
if not TOKEN and "--dry" not in sys.argv:
    print("Нет секрета TG_BOT_TOKEN — пропускаю"); sys.exit(0)
LATE_LIMIT = datetime.timedelta(hours=6)  # опоздавшее больше чем на 6 ч не публикуем
CONFIG = json.load(open("config.json", encoding="utf-8")) if os.path.exists("config.json") else {}
SHARE = "https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fbestfuneveningapp&text=" + \
        "%D0%97%D0%B0%D0%B3%D0%B0%D0%B4%D0%BA%D0%B8%20%D0%B8%20%D0%B8%D0%B3%D1%80%D1%8B%20%D0%B4%D0%BB%D1%8F%20%D0%BA%D0%BE%D0%BC%D0%BF%D0%B0%D0%BD%D0%B8%D0%B8%20%F0%9F%8E%B2"  # «Загадки и игры для компании 🎲»

now = datetime.datetime.now(datetime.timezone.utc)
schedule = json.load(open("schedule.json", encoding="utf-8"))
posted = json.load(open("posted.json", encoding="utf-8")) if os.path.exists("posted.json") else {}
dry = "--dry" in sys.argv

if not dry:  # проверка токена: имя бота и права в канале видны в логе
    me = subprocess.run(["curl", "-sS", f"https://api.telegram.org/bot{TOKEN}/getMe"], capture_output=True, text=True).stdout
    me = json.loads(me or "{}")
    print("бот:", me.get("result", {}).get("username") or f"ТОКЕН НЕ ПОДХОДИТ ({me.get('error_code')} {me.get('description')}, длина {len(TOKEN)}, пробелы: {TOKEN != TOKEN.strip()})")
    if me.get("ok"):
        cm = json.loads(subprocess.run(["curl", "-sS", f"https://api.telegram.org/bot{TOKEN}/getChatMember", "-d", f"chat_id={CHAT}", "-d", f"user_id={me['result']['id']}"], capture_output=True, text=True).stdout or "{}")
        r = cm.get("result", {})
        print("в канале:", r.get("status"), "может публиковать:", r.get("can_post_messages"), cm.get("description", ""))

def tg(method, **params):
    args = ["curl", "-sS", f"https://api.telegram.org/bot{TOKEN}/{method}"]
    for k, v in params.items():
        args += ["--form-string", f"{k}={v}"]
    return json.loads(subprocess.run(args, capture_output=True, text=True).stdout or "{}").get("result")

def linked_chat():
    """Чат обсуждения канала — туда идут посты с "to": "chat" (квиз-вечер)."""
    return (tg("getChat", chat_id=CHAT) or {}).get("linked_chat_id")

if not dry and TOKEN:  # раз в день — число подписчиков в stats.json
    stats = json.load(open("stats.json", encoding="utf-8")) if os.path.exists("stats.json") else {}
    day = (now + datetime.timedelta(hours=4)).date().isoformat()  # дата по Дубаю
    if day not in stats:
        n = tg("getChatMemberCount", chat_id=CHAT)
        if n:
            stats[day] = {"channel": n}
            chat = linked_chat()
            if chat:
                stats[day]["chat"] = tg("getChatMemberCount", chat_id=chat)
            json.dump(stats, open("stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("подписчики:", stats[day])

def buttons(item):
    """Кнопки под постом (включаются в config.json: "buttons": true)."""
    if not CONFIG.get("buttons") or item.get("buttons") is False or item["type"] == "poll":
        return []
    kb = [[{"text": "▶️ Сыграть", "url": "https://bfep.space/app/?s=tg-post-btn"},
           {"text": "📤 Отправить другу", "url": SHARE}]]
    return ["--form-string", "reply_markup=" + json.dumps({"inline_keyboard": kb}, ensure_ascii=False)]

def quiz_results(item):
    """Итоги квиз-вечера: кто сколько ответил верно (счёт ведёт bot.py в bot_state.json)."""
    st = json.load(open("bot_state.json", encoding="utf-8")) if os.path.exists("bot_state.json") else {}
    res = sorted(st.get("quiz", {}).get(item["quiz"], {}).items(), key=lambda kv: -kv[1])[:5]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    rows = "\n".join(f"{medals[i]} {st.get('names', {}).get(u, 'участник')} — {p}" for i, (u, p) in enumerate(res))
    return item["caption"].replace("{top}", rows or "в этот раз без победителя — ждём вас в следующую субботу!")

def send(item):
    method = {"video": "sendVideo", "photo": "sendPhoto", "text": "sendMessage", "poll": "sendPoll", "quiz_results": "sendMessage"}[item["type"]]
    chat = linked_chat() if item.get("to") == "chat" else CHAT
    if not chat:
        raise RuntimeError(f"{item['id']}: у канала нет чата обсуждения")
    args = ["curl", "-sS", "--fail-with-body", "--retry", "3",
            f"https://api.telegram.org/bot{TOKEN}/{method}", "--form-string", f"chat_id={chat}"]
    if item["type"] == "quiz_results":
        item = dict(item, type="text", caption=quiz_results(item))
    args += buttons(item)
    if item["type"] == "poll":  # опрос или викторина (quiz: correct — номер верного ответа с 0)
        args += ["--form-string", "question=" + item["question"],
                 "--form-string", "options=" + json.dumps(item["options"], ensure_ascii=False)]
        if "correct" in item:
            args += ["--form-string", "type=quiz", "--form-string", f"correct_option_id={item['correct']}"]
            if item.get("explanation"):
                args += ["--form-string", "explanation=" + item["explanation"]]
        if item.get("to") == "chat":  # в чате опрос не анонимный — так бот видит, кто ответил верно
            args += ["--form-string", "is_anonymous=false"]
    elif item["type"] == "text":
        args += ["--form-string", "text=" + item["caption"]]
    else:
        args += ["-F", f"{item['type']}=@{item['file']}", "--form-string", "caption=" + item.get("caption", "")]
        if item["type"] == "video":
            args += ["-F", "supports_streaming=true"]
    r = subprocess.run(args, capture_output=True, text=True)
    res = json.loads(r.stdout or "{}")
    if not res.get("ok"):
        raise RuntimeError(f"{item['id']}: {r.stdout or r.stderr}")
    if item.get("quiz") and "poll" in res["result"]:  # запомнить верный ответ для подсчёта в bot.py
        st = json.load(open("bot_state.json", encoding="utf-8")) if os.path.exists("bot_state.json") else {}
        st.setdefault("quiz_polls", {})[res["result"]["poll"]["id"]] = {"quiz": item["quiz"], "correct": item["correct"]}
        json.dump(st, open("bot_state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res["result"]["message_id"]

errors = 0
for item in schedule:
    if item["id"] in posted:
        continue
    at = datetime.datetime.fromisoformat(item["at_utc"].replace("Z", "+00:00"))
    if at > now:
        continue
    if now - at > LATE_LIMIT:
        posted[item["id"]] = {"skipped": "late", "at": now.isoformat()}
        print("пропущено (опоздание):", item["id"])
        continue
    if dry:
        print("опубликовал бы:", item["id"]); continue
    try:
        mid = send(item)
        posted[item["id"]] = {"message_id": mid, "at": now.isoformat()}
        print("опубликовано:", item["id"], mid)
    except Exception as e:
        errors += 1
        print("ОШИБКА:", e)

if not dry:
    json.dump(posted, open("posted.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.exit(1 if errors else 0)
