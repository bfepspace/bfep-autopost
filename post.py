"""Публикует в Telegram-канал всё, чему по schedule.json уже пора (бот: секрет TG_BOT_TOKEN)."""
import datetime, json, os, subprocess, sys

CHAT = os.environ.get("TG_CHAT", "@bestfuneveningapp")
TOKEN = os.environ.get("TG_BOT_TOKEN", "")
if not TOKEN and "--dry" not in sys.argv:
    print("Нет секрета TG_BOT_TOKEN — пропускаю"); sys.exit(0)
LATE_LIMIT = datetime.timedelta(hours=6)  # опоздавшее больше чем на 6 ч не публикуем

now = datetime.datetime.now(datetime.timezone.utc)
schedule = json.load(open("schedule.json", encoding="utf-8"))
posted = json.load(open("posted.json", encoding="utf-8")) if os.path.exists("posted.json") else {}
dry = "--dry" in sys.argv

if not dry:  # проверка токена: имя бота и права в канале видны в логе
    me = subprocess.run(["curl", "-sS", f"https://api.telegram.org/bot{TOKEN}/getMe"], capture_output=True, text=True).stdout
    me = json.loads(me or "{}")
    print("бот:", me.get("result", {}).get("username") or f"ТОКЕН НЕ ПОДХОДИТ ({me.get('error_code')} {me.get('description')}, длина {len(TOKEN)}, пробелы: {TOKEN != TOKEN.strip()})")

def send(item):
    method = {"video": "sendVideo", "photo": "sendPhoto", "text": "sendMessage"}[item["type"]]
    args = ["curl", "-sS", "--fail-with-body", "--retry", "3",
            f"https://api.telegram.org/bot{TOKEN}/{method}", "-F", f"chat_id={CHAT}"]
    if item["type"] == "text":
        args += ["-F", "text=" + item["caption"]]
    else:
        args += ["-F", f"{item['type']}=@{item['file']}", "-F", "caption=<-"]
        if item["type"] == "video":
            args += ["-F", "supports_streaming=true"]
    r = subprocess.run(args, input=item.get("caption", ""), capture_output=True, text=True)
    res = json.loads(r.stdout or "{}")
    if not res.get("ok"):
        raise RuntimeError(f"{item['id']}: {r.stdout or r.stderr}")
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
