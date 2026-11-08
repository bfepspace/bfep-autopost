"""Публикует в Discord-канал BEEZOO всё, чему по discord.json уже пора (вебхук: секрет DISCORD_WEBHOOK_URL).
Пункт с "hold": true не публикуется (ждёт OK Аркадия на сетку). Видео скачивается по "media" и прикрепляется файлом."""
import datetime, json, os, subprocess, sys, tempfile

HOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
dry = "--dry" in sys.argv
if not HOOK and not dry:
    print("Нет секрета DISCORD_WEBHOOK_URL — пропускаю Discord"); sys.exit(0)
LATE_LIMIT = datetime.timedelta(hours=6)
now = datetime.datetime.now(datetime.timezone.utc)
schedule = json.load(open("discord.json", encoding="utf-8")) if os.path.exists("discord.json") else []
posted = json.load(open("posted_discord.json", encoding="utf-8")) if os.path.exists("posted_discord.json") else {}

def send(item):
    payload = json.dumps({"content": item["text"], "username": "BEEZOO Space"}, ensure_ascii=False)
    args = ["curl", "-sS", "-o", "/dev/stdout", "-w", "\n%{http_code}", f"{HOOK}?wait=true", "-F", f"payload_json={payload}"]
    if item.get("media"):
        path = os.path.join(tempfile.gettempdir(), os.path.basename(item["media"]))
        subprocess.run(["curl", "-sSL", "-o", path, item["media"]], check=True)
        args += ["-F", f"files[0]=@{path}"]
    out = subprocess.run(args, capture_output=True, text=True).stdout.rsplit("\n", 1)
    code = out[-1].strip()
    if code not in ("200", "204"):
        print("Discord ошибка", code, out[0][:300]); return None
    return (json.loads(out[0] or "{}")).get("id", "ok")

changed = False
for item in schedule:
    if item["id"] in posted or item.get("hold"):
        continue
    at = datetime.datetime.fromisoformat(item["at_utc"].replace("Z", "+00:00"))
    if at > now:
        continue
    if now - at > LATE_LIMIT:
        posted[item["id"]] = {"skipped": "late", "at": now.isoformat()}; changed = True; continue
    if dry:
        print("опубликовал бы:", item["id"]); continue
    mid = send(item)
    if mid:
        posted[item["id"]] = {"message_id": mid, "at": now.isoformat()}; changed = True
        print("Discord:", item["id"])
if changed:
    json.dump(posted, open("posted_discord.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
