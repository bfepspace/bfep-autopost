"""Публикует в Snapchat BEEZOO Space через OneUp всё, чему по snap.json уже пора (секрет ONEUP_API_KEY).
Пост отправляется в OneUp в момент публикации (scheduled_date_time = сейчас + 3 мин по Дубаю), Spotlight.
python3 oneup_post.py --check  — проверить ключ и показать подключённые аккаунты и категории."""
import datetime, json, os, sys, urllib.error, urllib.parse, urllib.request

KEY = os.environ.get("ONEUP_API_KEY", "").strip()
API = "https://www.oneupapp.io/api/"
check = "--check" in sys.argv
dry = "--dry" in sys.argv
if not KEY and not dry:
    print("Нет секрета ONEUP_API_KEY — пропускаю Snapchat"); sys.exit(0)
LATE_LIMIT = datetime.timedelta(hours=6)
DUBAI = datetime.timezone(datetime.timedelta(hours=4))
now = datetime.datetime.now(datetime.timezone.utc)

UA = {"User-Agent": "Mozilla/5.0 (bfep-autopost)", "Accept": "application/json"}

def call(req):
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")

def get(ep, **p):
    p["apiKey"] = KEY
    req = urllib.request.Request(API + ep + "?" + urllib.parse.urlencode(p), headers=UA)
    return call(req)

def post(ep, **p):
    p["apiKey"] = KEY
    req = urllib.request.Request(API + ep, data=urllib.parse.urlencode(p).encode(), method="POST", headers=UA)
    return call(req)

if check:
    acc = get("listsocialaccounts")
    print("Аккаунты:", [(a.get("social_network_type"), a.get("username"), a.get("is_expired")) for a in acc.get("data", [])])
    cats = get("listcategory")
    print("Категории:", [(c.get("id"), c.get("category_name")) for c in cats.get("data", [])])
    if "--draft" in sys.argv:  # пробный черновик (не публикуется)
        it = json.load(open("snap.json", encoding="utf-8"))[0]
        when = (now + datetime.timedelta(days=1)).astimezone(DUBAI).strftime("%Y-%m-%d %H:%M")
        print("Черновик:", post("schedulevideopost", category_id=cats["data"][0]["id"], social_network_id="ALL",
              scheduled_date_time=when, content=it["text"], video_url=it["media"], title=it["text"][:90],
              snapchat=json.dumps({"isSpotLight": True}), isDraftPost="true"))
    sys.exit(0)

schedule = json.load(open("snap.json", encoding="utf-8")) if os.path.exists("snap.json") else []
posted = json.load(open("posted_snap.json", encoding="utf-8")) if os.path.exists("posted_snap.json") else {}
cat_id = None
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
    if cat_id is None:
        cats = get("listcategory").get("data", [])
        cat_id = os.environ.get("ONEUP_CATEGORY_ID") or (cats[0]["id"] if cats else "")
    when = (now + datetime.timedelta(minutes=3)).astimezone(DUBAI).strftime("%Y-%m-%d %H:%M")
    try:
        r = post("schedulevideopost", category_id=cat_id, social_network_id="ALL", scheduled_date_time=when,
                 content=item["text"], video_url=item["media"], title=item.get("title", item["text"][:90]),
                 snapchat=json.dumps({"isSpotLight": item.get("spotlight", True)}))
    except Exception as e:
        print("OneUp ошибка", item["id"], e); continue
    if r.get("error"):
        print("OneUp ошибка", item["id"], r); continue
    posted[item["id"]] = {"post_ids": r.get("post_ids"), "at": now.isoformat()}; changed = True
    print("Snapchat:", item["id"], r.get("message"))
if changed:
    json.dump(posted, open("posted_snap.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
