"""Бот в чате канала: отвечает участникам, считает загадки и приглашения (секрет TG_BOT_TOKEN).
Запуск: python3 bot.py 300 — слушает Telegram 300 секунд и выходит. Включается в config.json: "interactive": true."""
import datetime, json, os, random, re, subprocess, sys, time

TOKEN = os.environ.get("TG_BOT_TOKEN", "")
CHANNEL = os.environ.get("TG_CHAT", "@beezoospace")
CONFIG = json.load(open("config.json", encoding="utf-8")) if os.path.exists("config.json") else {}
RUN_FOR = int(sys.argv[1]) if len(sys.argv) > 1 else 300
APP = "https://bfep.space/app/?s=tg-chat-"
STATE_FILE = "bot_state.json"

if not TOKEN:
    time.sleep(RUN_FOR); sys.exit(0)

state = json.load(open(STATE_FILE, encoding="utf-8")) if os.path.exists(STATE_FILE) else {}
state.setdefault("offset", 0); state.setdefault("riddles", {}); state.setdefault("scores", {})
state.setdefault("names", {}); state.setdefault("invites", {}); state.setdefault("recent", [])
state["recent"] = [n for n in state["recent"] if n not in ("Group", "Telegram", "Channel")]

def api(method, **params):
    args = ["curl", "-sS", "--max-time", "70", f"https://api.telegram.org/bot{TOKEN}/{method}"]
    for k, v in params.items():
        args += ["--form-string", f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}"]
    r = json.loads(subprocess.run(args, capture_output=True, text=True).stdout or "{}")
    if not r.get("ok"):
        print("Telegram:", method, r.get("error_code"), r.get("description"))
    return r.get("result")

def play(place, text="▶️ Играть в приложении"):
    return {"inline_keyboard": [[{"text": text, "url": APP + place}]]}

def reply(msg, text, place=None, html=False):
    p = {"chat_id": msg["chat"]["id"], "text": text, "reply_to_message_id": msg["message_id"]}
    if html:
        p["parse_mode"] = "HTML"
    if place:
        p["reply_markup"] = play(place)
    return api("sendMessage", **p)

def norm(s):
    return re.sub(r"[^\wё ]", " ", s.lower().replace("ё", "е")).split()

def week():
    return datetime.date.today().strftime("%G-W%V")

def add_score(user, pts):
    w = state["scores"].setdefault(week(), {})
    w[str(user["id"])] = w.get(str(user["id"]), 0) + pts
    state["names"][str(user["id"])] = user.get("first_name", "участник")

def top(n=5):
    w = state["scores"].get(week(), {})
    rows = sorted(w.items(), key=lambda kv: -kv[1])[:n]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    return "\n".join(f"{medals[i]} {state['names'].get(u, 'участник')} — {p}" for i, (u, p) in enumerate(rows))

def riddle_answer(date):
    """Ответ на загадку берём из подписи следующей загадки в schedule.json («✅ Ответ на вчерашнюю: …»)."""
    nxt = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
    schedule = json.load(open("schedule.json", encoding="utf-8"))
    for item in schedule:  # ответ можно указать прямо у загадки: "answer"
        if item["id"] == f"z-{date}" and item.get("answer"):
            return item["answer"]
    for item in schedule:
        if item["id"] == f"z-{nxt}":
            m = re.search(r"Ответ на вчерашнюю:\s*(.+?)\.?\n", item["caption"])
            return m.group(1) if m else None
    return None

def is_correct(text, answer):
    key = [w for w in norm(answer) if len(w) > 2 and w not in ("около", "минут")] or norm(answer)
    words = norm(text)
    return any(any(w.startswith(k[:max(4, len(k) - 2)]) for w in words) for k in key)

def on_channel_post(msg):
    """Пост канала пришёл в чат обсуждения: первый комментарий бота."""
    text = msg.get("caption") or msg.get("text") or ""
    if "Загадка дня" in text:
        date = datetime.date.today().isoformat()
        for d, r in state["riddles"].items():  # итог вчерашней загадки — в её же комментариях
            if not r.get("closed"):
                names = ", ".join(r["winners"]) or "никто — эта была сложной"
                api("sendMessage", chat_id=msg["chat"]["id"], reply_to_message_id=r["thread"],
                    text=f"⏰ Время вышло! Первыми угадали: {names}.\n\n🏆 Очки недели:\n{top() or 'пока пусто'}")
                r["closed"] = True
        state["riddles"][date] = {"thread": msg["message_id"], "answer": riddle_answer(date), "winners": []}
        api("sendMessage", chat_id=msg["chat"]["id"], reply_to_message_id=msg["message_id"],
            text="🧩 Ваши версии — ответом сюда 👇\nПервые трое, кто угадает, получат 3, 2 и 1 очко. Таблица недели — /top")
    elif "Итоги недели" in text:
        api("sendMessage", chat_id=msg["chat"]["id"], reply_to_message_id=msg["message_id"],
            text=f"🏆 Лучшие отгадчики недели:\n{top() or 'пока никого — в понедельник новая неделя!'}\n\nПозови друзей в команду: /invite")
    else:
        # защита от повторов (16.11 под одним постом ушло 15+ одинаковых вопросов): один комментарий на пост канала
        key = str(msg.get("forward_from_message_id") or (msg.get("forward_origin") or {}).get("message_id") or msg["message_id"])
        done = state.setdefault("commented", [])
        if key in done:
            print("повтор поста канала", key, "— комментарий не отправляю"); return
        done.append(key); del done[:-200]
        save()  # фиксируем до отправки: даже при сбое повторного комментария не будет
        q = random.choice(CONFIG.get("first_comments") or ["А у вас в компании так бывает? 👇"])
        api("sendMessage", chat_id=msg["chat"]["id"], reply_to_message_id=msg["message_id"], text=q)

def on_riddle_reply(msg):
    thread = (msg.get("reply_to_message") or {}).get("message_id")
    for r in state["riddles"].values():
        if r["thread"] == thread or msg.get("message_thread_id") == r["thread"]:
            if r.get("closed") or not r.get("answer"):
                return False
            name = msg["from"].get("first_name", "участник")
            if name in r["winners"] or len(r["winners"]) >= 3 or not is_correct(msg.get("text", ""), r["answer"]):
                return True
            r["winners"].append(name)
            add_score(msg["from"], 4 - len(r["winners"]))
            api("setMessageReaction", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                reaction=[{"type": "emoji", "emoji": "🔥"}])
            return True
    return False

def on_command(msg, cmd, arg):
    user = msg["from"]
    if cmd in ("start", "help", "помощь"):
        reply(msg, "Привет! Я бот BEEZOO Space 🎲\n\n/riddle — загадка\n/dice — бросить кубик\n/wheel а, б, в — колесо решений\n"
                   "/who — кто сегодня … (выберу случайного)\n/top — очки недели\n/invite — твоя ссылка для друзей", "start")
    elif cmd in ("riddle", "загадка"):
        r = random.choice(CONFIG.get("riddles") or [["Что идёт, не двигаясь с места?", "время"]])
        reply(msg, f"🧩 {r[0]}\n\nОтвет (нажми): <tg-spoiler>{r[1]}</tg-spoiler>", "riddle", html=True)
    elif cmd in ("dice", "кубик"):
        api("sendDice", chat_id=msg["chat"]["id"], emoji="🎲", reply_to_message_id=msg["message_id"])
    elif cmd in ("wheel", "колесо"):
        opts = [o.strip() for o in re.split(r"[,;\n]| или ", arg) if o.strip()] or ["да", "нет"]
        reply(msg, f"🎡 Колесо решило: {random.choice(opts)}!\n\nВ приложении — колесо с анимацией и звуком 👇", "wheel")
    elif cmd in ("who", "кто"):
        people = [p for p in state["recent"] if p] or [user.get("first_name", "ты")]
        reply(msg, f"☝️ Выбор пал на: {random.choice(people)}! {('— ' + arg) if arg else ''}\n\n«Выбор пальцем» для всей компании — в приложении 👇", "who")
    elif cmd in ("top", "очки"):
        reply(msg, f"🏆 Очки недели:\n{top() or 'пока пусто — угадай загадку дня первым!'}")
    elif cmd in ("invite", "пригласить"):
        uid = str(user["id"])
        if uid not in state["invites"]:
            link = api("createChatInviteLink", chat_id=CHANNEL, name=f"ref:{uid}")
            if not link:
                return reply(msg, "Не получилось сделать ссылку, попробуй позже 🙏")
            state["invites"][uid] = {"link": link["invite_link"], "count": 0}
        state["names"][uid] = user.get("first_name", "участник")
        inv = state["invites"][uid]
        reply(msg, f"📨 Твоя личная ссылка на канал:\n{inv['link']}\n\nУже пришло по ней: {inv['count']}. Лучших назовём в «Итогах недели» "
                   "и позовём первыми тестировать новые игры!")

def on_join(upd):
    """Кто-то вступил в канал по личной ссылке — засчитываем пригласившему."""
    cm = upd["chat_member"]
    name = (cm.get("invite_link") or {}).get("name", "")
    if cm["new_chat_member"]["status"] == "member" and cm["old_chat_member"]["status"] in ("left", "kicked") and name.startswith("ref:"):
        uid = name[4:]
        if uid in state["invites"]:
            state["invites"][uid]["count"] += 1
            add_score({"id": int(uid), "first_name": state["names"].get(uid, "участник")}, 5)

def on_poll_answer(pa):
    """Ответ на вопрос квиз-вечера: +1 в квизе и +2 очка недели за верный."""
    q = state.get("quiz_polls", {}).get(pa["poll_id"])
    user = pa.get("user")
    if q and user and pa["option_ids"] == [q["correct"]]:
        board = state.setdefault("quiz", {}).setdefault(q["quiz"], {})
        board[str(user["id"])] = board.get(str(user["id"]), 0) + 1
        add_score(user, 2)

def handle(upd):
    if "poll_answer" in upd:
        return on_poll_answer(upd["poll_answer"])
    if "chat_member" in upd:
        return on_join(upd)
    msg = upd.get("message")
    if not msg:
        return
    if msg.get("is_automatic_forward"):
        return on_channel_post(msg)
    for m in msg.get("new_chat_members", []):
        if not m.get("is_bot"):
            api("sendMessage", chat_id=msg["chat"]["id"], reply_markup=play("welcome"),
                text=f"👋 {m.get('first_name', '')}, добро пожаловать в BEEZOO Space!\nКаждый день в 10:00 — загадка, угадывай первым. Команды: /help")
    user = msg.get("from") or {}
    if user.get("is_bot") or user.get("id") in (777000, 1087968824, 136817688):  # служебные отправители: канал, анонимный админ
        user = {}
    if user.get("first_name") and msg["chat"]["type"] != "private":
        state["recent"] = ([user["first_name"]] + [n for n in state["recent"] if n != user["first_name"]])[:20]
    text = msg.get("text", "")
    m = re.match(r"^/(\w+)(?:@\w+)?\s*(.*)", text, re.S)
    if m:
        return on_command(msg, m.group(1).lower(), m.group(2))
    on_riddle_reply(msg)

def save():
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def cleanup_dups():
    """Разовая чистка 16.11: лишние первые комментарии бота под последним постом канала.
    Свои сообщения узнаём так: editMessageReplyMarkup без изменений отвечает «not modified» только на сообщения бота.
    Идём от самого нового сообщения чата вниз, пока сообщения — бота; самое раннее из них оставляем, остальные удаляем."""
    task = CONFIG.get("tg_cleanup")
    if not task or state.get("cleanup_done") == task:
        return
    log = state.setdefault("cleanup_log", [])
    chat = (api("getChat", chat_id=CHANNEL) or {}).get("linked_chat_id")
    if not chat:
        log.append("нет linked_chat_id"); return
    def probe(mid):
        args = ["curl", "-sS", "--max-time", "20", f"https://api.telegram.org/bot{TOKEN}/editMessageReplyMarkup",
                "--form-string", f"chat_id={chat}", "--form-string", f"message_id={mid}"]
        r = json.loads(subprocess.run(args, capture_output=True, text=True).stdout or "{}")
        d = (r.get("description") or "").lower()
        if r.get("ok"):
            return "own"  # не должно случаться: разметки не было
        if "not modified" in d:
            return "own"
        if "not found" in d:
            return "none"
        return "foreign"
    base = max([r["thread"] for r in state["riddles"].values()] or [1])
    if str(task).endswith("scan"):  # только осмотр: какие сообщения после загадки чьи (own/foreign/none)
        log.append({"scan_from": base, "kinds": {m: probe(m) for m in range(base, base + 60)}})
        state["cleanup_done"] = task; save(); return
    top, miss, mid = base, 0, base
    while miss < 40 and mid < base + 2000:
        mid += 1
        if probe(mid) == "none":
            miss += 1
        else:
            top, miss = mid, 0
    run, mid = [], top
    while mid > base:
        k = probe(mid)
        if k == "own":
            run.append(mid)
        elif k == "foreign":
            break
        mid -= 1
    keep = min(run) if run else None
    gone = []
    for m in sorted(run)[1:][:60]:
        if api("deleteMessage", chat_id=chat, message_id=m):
            gone.append(m)
    log.append({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "chat": chat, "top": top, "stop_at": mid,
                "kept": keep, "deleted": gone})
    state["cleanup_done"] = task
    save()

cleanup_dups()
if not CONFIG.get("interactive"):
    save(); time.sleep(RUN_FOR); sys.exit(0)

end = time.time() + RUN_FOR
while time.time() < end:
    ups = api("getUpdates", offset=state["offset"], timeout=max(1, min(50, int(end - time.time()))),
              allowed_updates=["message", "chat_member", "poll_answer"]) or []
    for u in ups:
        if u["update_id"] < state["offset"]:
            continue  # уже обработан
        state["offset"] = u["update_id"] + 1
        save()  # offset сохраняем сразу, до обработки
        try:
            handle(u)
        except Exception as e:
            print("ОШИБКА:", e)
    if ups:
        save()
    elif ups is None:
        time.sleep(10)  # например, у бота стоит webhook (409) — не долбим Telegram
