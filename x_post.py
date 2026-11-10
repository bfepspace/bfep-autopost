"""Публикует в X (@beezoospace) всё, чему по x.json уже пора. Ключи — секреты GitHub:
X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET (OAuth 1.0a, права Read and write).
Пункт с "hold": true не публикуется (ждёт OK Аркадия). Видео: скачать по "media" → загрузка частями → пост.
Оплата X — за каждый пост (≈$0,015), поэтому ссылок в тексте нет (пост со ссылкой ≈$0,20)."""
import base64, datetime, hashlib, hmac, json, os, secrets, subprocess, sys, tempfile, time, urllib.parse, urllib.request

K = {n: os.environ.get(n, "").strip() for n in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
dry = "--dry" in sys.argv
if not all(K.values()) and not dry:
    print("Нет ключей X_* — пропускаю X"); sys.exit(0)
API = "https://api.x.com/2"
LATE_LIMIT = datetime.timedelta(hours=6)
CHUNK = 4 * 1024 * 1024
q = lambda s: urllib.parse.quote(str(s), safe="~")

def auth(method, url, query=None):
    """Заголовок OAuth 1.0a (тело JSON/multipart в подпись не входит, query — входит)."""
    o = {"oauth_consumer_key": K["X_API_KEY"], "oauth_nonce": secrets.token_hex(16),
         "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
         "oauth_token": K["X_ACCESS_TOKEN"], "oauth_version": "1.0"}
    params = {**(query or {}), **o}
    base = "&".join([method, q(url), q("&".join(f"{q(k)}={q(v)}" for k, v in sorted(params.items())))])
    key = f"{q(K['X_API_SECRET'])}&{q(K['X_ACCESS_SECRET'])}"
    o["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{k}="{q(v)}"' for k, v in sorted(o.items()))

def call(method, path, query=None, body=None, ctype="application/json"):
    url = API + path
    full = url + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(full, data=body, method=method,
                                 headers={"Authorization": auth(method, url, query), **({"Content-Type": ctype} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"X {method} {path} → {e.code}: {e.read()[:400]!r}")

if "--check" in sys.argv:  # проверка ключей без публикации (workflow x-check)
    try: print("X ключи OK, аккаунт:", call("GET", "/users/me").get("data", {}).get("username")); sys.exit(0)
    except RuntimeError as e: print("X ключи НЕ принимаются:", e); sys.exit(1)

def multipart(fields, fname, data):
    b = "----beezoo" + secrets.token_hex(8)
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += f'--{b}\r\nContent-Disposition: form-data; name="media"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + data + f"\r\n--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"

def upload_video(path):
    size = os.path.getsize(path)
    init = call("POST", "/media/upload/initialize",
                body=json.dumps({"media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"}).encode())
    mid = init["data"]["id"]
    with open(path, "rb") as f:
        i = 0
        while chunk := f.read(CHUNK):
            body, ct = multipart({"segment_index": i}, os.path.basename(path), chunk)
            call("POST", f"/media/upload/{mid}/append", body=body, ctype=ct); i += 1
    info = call("POST", f"/media/upload/{mid}/finalize").get("data", {}).get("processing_info")
    while info and info.get("state") in ("pending", "in_progress"):
        time.sleep(max(2, int(info.get("check_after_secs", 5))))
        info = call("GET", "/media/upload", query={"command": "STATUS", "media_id": mid}).get("data", {}).get("processing_info")
    if info and info.get("state") == "failed":
        raise RuntimeError(f"X: видео не обработано: {info}")
    return mid

def send(item):
    body = {"text": item["text"]}
    if item.get("media"):
        path = os.path.join(tempfile.gettempdir(), os.path.basename(item["media"]))
        subprocess.run(["curl", "-sSL", "-o", path, item["media"]], check=True)
        body["media"] = {"media_ids": [upload_video(path)]}
    return call("POST", "/tweets", body=json.dumps(body, ensure_ascii=False).encode())["data"]["id"]

now = datetime.datetime.now(datetime.timezone.utc)
schedule = json.load(open("x.json", encoding="utf-8")) if os.path.exists("x.json") else []
posted = json.load(open("posted_x.json", encoding="utf-8")) if os.path.exists("posted_x.json") else {}
changed = False
for item in schedule:
    if item["id"] in posted or item.get("hold"):
        continue
    assert "http" not in item["text"] and "bfep.space" not in item["text"] and "beezoo.space" not in item["text"], "в X без ссылок"
    at = datetime.datetime.fromisoformat(item["at_utc"].replace("Z", "+00:00"))
    if at > now:
        continue
    if now - at > LATE_LIMIT:
        posted[item["id"]] = {"skipped": "late", "at": now.isoformat()}; changed = True; continue
    if dry:
        print("опубликовал бы:", item["id"], len(item["text"]), "симв."); continue
    try:
        tid = send(item)
    except Exception as e:
        print("X ошибка", item["id"], e)
        if " 401" in str(e):  # диагностика: ключи вообще принимаются?
            try: print("X ключи OK, аккаунт:", call("GET", "/users/me").get("data", {}).get("username"))
            except Exception as e2: print("X ключи НЕ принимаются:", e2)
        continue
    posted[item["id"]] = {"tweet_id": tid, "at": now.isoformat()}; changed = True
    print("X:", item["id"], tid)
if changed:
    json.dump(posted, open("posted_x.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
