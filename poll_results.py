"""Собирает итоги еженедельных опросов (id начинается с "poll-") в poll_results.json, когда опрос закрылся (через 48 ч).
Telegram: stopPoll по message_id из posted.json — закрывает опрос и возвращает голоса.
Discord: GET сообщения через вебхук — poll.results.answer_counts.
X: GET твита с expansions=attachments.poll_ids — голоса по вариантам (чтение стоит кредитов, поэтому один раз на опрос)."""
import datetime, json, os, subprocess, sys
now = datetime.datetime.now(datetime.timezone.utc)
RES = "poll_results.json"
res = json.load(open(RES, encoding="utf-8")) if os.path.exists(RES) else {}
load = lambda f: json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
changed = False

def due(entry, hours=48):
    at = datetime.datetime.fromisoformat(entry["at"])
    return now - at > datetime.timedelta(hours=hours, minutes=10)

def tg(item_id, entry):
    tok = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat = os.environ.get("TG_CHAT", "@beezoospace")
    out = subprocess.run(["curl", "-sS", "--max-time", "60", f"https://api.telegram.org/bot{tok}/stopPoll",
                          "--form-string", f"chat_id={chat}", "--form-string", f"message_id={entry['message_id']}"],
                         capture_output=True, text=True).stdout
    r = json.loads(out or "{}")
    if not r.get("ok"):
        print("TG итоги ошибка", item_id, out[:200]); return None
    return {o["text"]: o["voter_count"] for o in r["result"]["options"]}

def dc(item_id, entry):
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    out = subprocess.run(["curl", "-sS", "--max-time", "60", f"{hook}/messages/{entry['message_id']}"], capture_output=True, text=True).stdout
    m = json.loads(out or "{}")
    p = m.get("poll")
    if not p:
        print("Discord итоги ошибка", item_id, out[:200]); return None
    counts = {c["id"]: c["count"] for c in (p.get("results") or {}).get("answer_counts", [])}
    return {a["poll_media"]["text"]: counts.get(a["answer_id"], 0) for a in p["answers"]}

def xx(item_id, entry):
    src = open("x_post.py", encoding="utf-8").read().split("PAUSE =")[0]  # только функции подписи и call(), без публикации
    g = {"__name__": "x_api"}; exec(src, g)
    r = g["call"]("GET", f"/tweets/{entry['tweet_id']}", query={"expansions": "attachments.poll_ids", "poll.fields": "options,voting_status"})
    polls = r.get("includes", {}).get("polls", [])
    if not polls:
        print("X итоги ошибка", item_id, str(r)[:200]); return None
    return {o["label"]: o["votes"] for o in polls[0]["options"]}

for fname, net, fn in (("posted.json", "telegram", tg), ("posted_discord.json", "discord", dc), ("posted_x.json", "x", xx)):
    for item_id, entry in load(fname).items():
        if not item_id.startswith("poll-") or "at" not in entry or "skipped" in entry:
            continue
        key = f"{net}:{item_id}"
        if key in res or not due(entry):
            continue
        if "--dry" in sys.argv:
            print("собрал бы:", key); continue
        try:
            votes = fn(item_id, entry)
        except Exception as e:
            print("итоги ошибка", key, e); continue
        if votes is not None:
            res[key] = {"votes": votes, "total": sum(votes.values()), "at": now.isoformat()}; changed = True
            print("Итоги", key, votes)
if changed:
    json.dump(res, open(RES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
