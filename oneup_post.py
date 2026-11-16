"""Публикует через OneUp всё, чему уже пора (секрет ONEUP_API_KEY):
snap.json → Snapchat BEEZOO Space (Spotlight), bs.json → Bluesky @beezoospace.bsky.social.
Каждый пост уходит только в аккаунт своей сети (social_network_id по listsocialaccounts), не в ALL.
Пост отправляется в OneUp в момент публикации (scheduled_date_time = сейчас + 3 мин по Дубаю).
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

def vurl(u):
    """raw.githubusercontent отдаёт octet-stream — OneUp его не принимает; jsDelivr отдаёт video/mp4."""
    pre = "https://raw.githubusercontent.com/"
    if u.startswith(pre):
        owner, repo, ref, path = u[len(pre):].split("/", 3)
        return f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}"
    return u

def get(ep, **p):
    p["apiKey"] = KEY
    req = urllib.request.Request(API + ep + "?" + urllib.parse.urlencode(p), headers=UA)
    return call(req)

def post(ep, **p):
    p["apiKey"] = KEY
    req = urllib.request.Request(API + ep, data=urllib.parse.urlencode(p).encode(), method="POST", headers=UA)
    return call(req)

NETS = [("snap.json", "posted_snap.json", "snap", "Snapchat"), ("bs.json", "posted_bs.json", "bluesky", "Bluesky")]
_acc = None

def account_ids(kind):
    """id аккаунтов OneUp нужной сети. Не нашли — None (тогда пост не отправляем, чтобы не уйти во все сети)."""
    global _acc
    if _acc is None:
        _acc = get("listsocialaccounts").get("data", [])
    ids = [str(a.get("social_account_id") or a.get("social_network_id") or a.get("id")) for a in _acc
           if kind in str(a.get("social_network_type", "")).lower() and not a.get("is_expired")]
    if ids:
        return json.dumps(ids)
    if kind == "snap" and len(_acc) == 1:  # до появления второй сети работало с ALL
        return "ALL"
    print("OneUp: не найден аккаунт", kind, [(a.get("social_network_type"), a.get("username")) for a in _acc])
    return None

if check:
    acc = get("listsocialaccounts")
    print("Аккаунты:", [{k: v for k, v in a.items() if "token" not in k.lower()} for a in acc.get("data", [])])
    cats = get("listcategory")
    print("Категории:", [(c.get("id"), c.get("category_name")) for c in cats.get("data", [])])
    for u in [vurl(i["media"]) for i in json.load(open("snap.json", encoding="utf-8"))[-3:]]:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                print("HEAD", r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length"), u)
        except Exception as e:
            print("HEAD ошибка", e, u)
    if "--draft" in sys.argv:  # пробный черновик (не публикуется)
        it = json.load(open("snap.json", encoding="utf-8"))[0]
        when = (now + datetime.timedelta(days=1)).astimezone(DUBAI).strftime("%Y-%m-%d %H:%M")
        print("Черновик:", post("schedulevideopost", category_id=cats["data"][0]["id"], social_network_id=account_ids("snap"),
              scheduled_date_time=when, content=it["text"], video_url=vurl(it["media"]), title=it["text"][:90],
              snapchat=json.dumps({"isSpotLight": True}), isDraftPost="true"))
    sys.exit(0)

cat_id = None
for fname, pname, kind, label in NETS:
    schedule = json.load(open(fname, encoding="utf-8")) if os.path.exists(fname) else []
    posted = json.load(open(pname, encoding="utf-8")) if os.path.exists(pname) else {}
    changed = False
    net_ids = False
    for item in schedule:
        if item["id"] in posted or item.get("hold"):
            continue
        at = datetime.datetime.fromisoformat(item["at_utc"].replace("Z", "+00:00"))
        if at > now:
            continue
        if now - at > LATE_LIMIT:
            posted[item["id"]] = {"skipped": "late", "at": now.isoformat()}; changed = True; continue
        if dry:
            print("опубликовал бы:", label, item["id"]); continue
        if net_ids is False:
            net_ids = account_ids(kind)
        if net_ids is None:
            break
        if cat_id is None:
            cats = get("listcategory").get("data", [])
            cat_id = os.environ.get("ONEUP_CATEGORY_ID") or (cats[0]["id"] if cats else "")
        when = (now + datetime.timedelta(minutes=3)).astimezone(DUBAI).strftime("%Y-%m-%d %H:%M")
        extra = {"snapchat": json.dumps({"isSpotLight": item.get("spotlight", True)})} if kind == "snap" else {}
        try:
            if item.get("media"):
                r = post("schedulevideopost", category_id=cat_id, social_network_id=net_ids, scheduled_date_time=when,
                         content=item["text"], video_url=vurl(item["media"]), title=item.get("title", item["text"][:90]), **extra)
            else:
                r = post("scheduletextpost", category_id=cat_id, social_network_id=net_ids, scheduled_date_time=when,
                         content=item["text"])
        except Exception as e:
            print("OneUp ошибка", label, item["id"], e); continue
        if r.get("error"):
            print("OneUp ошибка", label, item["id"], r); continue
        posted[item["id"]] = {"post_ids": r.get("post_ids"), "at": now.isoformat()}; changed = True
        print(label + ":", item["id"], r.get("message"))
    if changed:
        json.dump(posted, open(pname, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
