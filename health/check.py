"""Проверка связей BEEZOO/BFEP (принцип «необходимо и достаточно»): всё, что при поломке теряет людей, записи или публикации.
Запуск: python3 health/check.py <папка с клоном bfep-site>. Пишет health/report.json и health/report.md.
Ничего не публикует и ничего не меняет вне папки health/."""
import datetime, hashlib, json, os, re, socket, ssl, subprocess, sys, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = sys.argv[1] if len(sys.argv) > 1 else None
T = json.load(open(os.path.join(ROOT, "health", "targets.json"), encoding="utf-8"))
NOW = datetime.datetime.now(datetime.timezone.utc)
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) bfep-health"}
R = []  # {area, name, status: ok|warn|fail, detail}

def add(area, name, status, detail=""):
    R.append({"area": area, "name": name, "status": status, "detail": str(detail)[:300]})

def fetch(url, body=False, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.geturl(), (r.read() if body else b"")
    except urllib.error.HTTPError as e:
        return e.code, url, b""
    except Exception as e:
        return 0, url, str(e).encode()

def judge(t, area):
    name = t.get("name") or t["url"]
    code, final, b = fetch(t["url"], body=bool(t.get("must")))
    k = t.get("kind", "page")
    if k == "optional":
        add(area, name, "ok" if 0 < code < 400 else "warn", f"{code}")
    elif k == "soft":
        add(area, name, "fail" if code == 404 else "warn" if code == 0 else "ok", f"{code}")
    elif k == "alive":
        add(area, name, "ok" if 0 < code < 500 else "fail", f"{code}")
    elif code == 200 and (not t.get("must") or t["must"].encode() in b):
        add(area, name, "ok", final if final != t["url"] else "200")
    elif code == 200:
        add(area, name, "fail", f"открывается, но нет «{t['must']}»")
    else:
        add(area, name, "fail", f"{code} {b[:120].decode(errors='replace') if code == 0 else ''}")

# 1. Сайты, страницы, счётчики, соцсети
targets = [(t, "Сайт") for t in T["sites"]] + [(t, "Сервисы") for t in T["third_party"]] + [(t, "Соцсети") for t in T["social"]]
for g in T["games"]:
    targets += [({"url": f"https://bfep.space/{g}/", "kind": "page", "name": f"Умная ссылка bfep.space/{g}"}, "Игры"),
                ({"url": f"https://bfep.space/play/{g}/", "kind": "page", "name": f"Игра в браузере /play/{g}/"}, "Игры")]
with ThreadPoolExecutor(12) as ex:
    list(ex.map(lambda p: judge(*p), targets))

# 2. Сайт выложен целиком: живая главная = репозиторий; все внутренние ссылки открываются
if SITE and os.path.isdir(SITE):
    code, _, live = fetch("https://bfep.space/", body=True)
    repo = open(os.path.join(SITE, "index.html"), "rb").read()
    def vmax(b):
        v = [tuple(map(int, x.split(b"."))) for x in re.findall(rb"\?v=(\d+\.\d+)", b)]
        return ".".join(map(str, max(v))) if v else "?"
    lv, rv = vmax(live), vmax(repo)
    same = hashlib.sha1(live).hexdigest() == hashlib.sha1(repo).hexdigest()
    add("Сайт", "Живой сайт = последняя версия в репозитории", "ok" if same or lv == rv else "warn",
        f"на сайте метки до v{lv}, в репозитории до v{rv}" + ("" if same else " (главная отличается побайтно)"))
    paths = set()
    for dp, _, fs in os.walk(SITE):
        if "/.git" in dp: continue
        for f in fs:
            if f.endswith((".html", ".js")):
                txt = open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read()
                for m in re.findall(r'(?:href|src)=["\'](/[^"\'#?\s${}+]*)', txt):
                    if m.startswith("//"): continue
                    if m.endswith("/") and not os.path.exists(os.path.join(SITE, m.strip("/"), "index.html")) and m != "/": continue  # начало адреса из кода ('/play/' + id)
                    paths.add(m)
    bad = []
    def chk(p):
        c, _, _ = fetch("https://bfep.space" + p, method="GET")
        if c != 200: bad.append(f"{p} → {c}")
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(chk, sorted(paths)))
    add("Сайт", f"Внутренние ссылки и картинки ({len(paths)})", "ok" if not bad else "fail", "; ".join(sorted(bad)[:15]))

# 3. Формы листа ожидания Brevo (6 языков) — адрес формы отвечает
code, _, wl = fetch("https://bfep.space/smart/waitlist.html", body=True)
forms = dict(re.findall(rb'(\w\w): "(https://[\w.]+sibforms\.com/serve/[^"]+)"', wl))
if not forms:
    add("Лист ожидания", "Адреса форм Brevo на сайте", "fail", "не найдены в smart/waitlist.html")
for l, u in sorted(forms.items()):
    # Пробная отправка с заведомо неверной почтой: контакт не создаётся, но Brevo должен ответить JSON с ошибкой EMAIL
    import urllib.parse
    data = urllib.parse.urlencode({"EMAIL": "health-check-not-an-email", "OPT_IN": "1", "email_address_check": "", "locale": l.decode(), "html_type": "simple",
                                   "GAME": "all", "SOURCE": "health", "CAMPAIGN": "health"}).encode()
    req = urllib.request.Request(u.decode() + "?isAjax=1", data=data, headers=dict(UA, Origin="https://bfep.space"), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            c, body, cors = r.status, r.read().decode(errors="replace"), r.headers.get("Access-Control-Allow-Origin", "")
    except urllib.error.HTTPError as e:
        c, body, cors = e.code, e.read().decode(errors="replace"), e.headers.get("Access-Control-Allow-Origin", "")
    except Exception as e:
        c, body, cors = 0, str(e), ""
    try: j = json.loads(body)
    except Exception: j = None
    other = [k for k in ((j or {}).get("errors") or {}) if k.upper() != "EMAIL"] if isinstance((j or {}).get("errors"), dict) else []
    st = "ok" if j is not None and not other else "fail"
    add("Лист ожидания", f"Форма Brevo {l.decode().upper()}", st,
        f"{c}; ответ {'JSON' if j is not None else 'не JSON'}; CORS {'да' if cors else 'нет (сайт шлёт вслепую)'}" + (f"; лишние поля: {other}" if other else "") + ("" if j is not None else "; " + body[:120]))
if forms and b"isAjax" not in wl and b"no-cors" in wl:
    add("Лист ожидания", "Ошибки отправки видны посетителю", "warn", "отправка no-cors: при сбое Brevo человек всё равно видит «Готово»")

# 4. SSL-сертификаты
for d in T["ssl_domains"]:
    try:
        with socket.create_connection((d, 443), timeout=15) as s, ssl.create_default_context().wrap_socket(s, server_hostname=d) as ss:
            exp = datetime.datetime.strptime(ss.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)
        days = (exp - NOW).days
        add("Домены", f"SSL {d}", "ok" if days > 20 else "warn" if days > 7 else "fail", f"ещё {days} дн.")
    except Exception as e:
        add("Домены", f"SSL {d}", "fail", e)

# 5. Очереди автопостинга: просрочки, пропуски, файлы и ссылки на ближайшие 14 дней
def ts(s): return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
for q in T["queues"]:
    fp = os.path.join(ROOT, q["file"])
    if not os.path.exists(fp): continue
    items = json.load(open(fp, encoding="utf-8"))
    pp = os.path.join(ROOT, q["posted"])
    posted = json.load(open(pp, encoding="utf-8")) if os.path.exists(pp) else {}
    overdue = [i["id"] for i in items if not i.get("hold") and i["id"] not in posted and NOW - ts(i["at_utc"]) > datetime.timedelta(hours=2)]
    week = NOW - datetime.timedelta(days=7)
    skipped = [k for k, v in posted.items() if isinstance(v, dict) and v.get("skipped") and ts(v["at"]) > week]
    add("Автопостинг", f"{q['name']}: всё вышло вовремя", "fail" if overdue else "warn" if skipped else "ok",
        ("не вышли: " + ", ".join(overdue[:8]) if overdue else "") + (" пропущены за неделю: " + ", ".join(skipped[:8]) if skipped else ""))
    soon = [i for i in items if not i.get("hold") and i["id"] not in posted and NOW <= ts(i["at_utc"]) <= NOW + datetime.timedelta(days=14)]
    missing = []
    for i in soon:
        m = i.get("file") or i.get("media")
        if not m: continue
        if m.startswith("http"):
            if fetch(m, method="HEAD")[0] != 200: missing.append(i["id"])
        elif not os.path.exists(os.path.join(ROOT, m)): missing.append(i["id"])
    hold = [i["id"] for i in items if i.get("hold") and NOW <= ts(i["at_utc"]) <= NOW + datetime.timedelta(days=7)]
    last = max([ts(i["at_utc"]) for i in items], default=NOW)
    add("Автопостинг", f"{q['name']}: файлы на 14 дней ({len(soon)} постов)", "fail" if missing else "ok", ", ".join(missing[:8]))
    if hold: add("Автопостинг", f"{q['name']}: ждут OK в ближайшие 7 дней", "warn", ", ".join(hold[:8]))
    add("Автопостинг", f"{q['name']}: запас контента", "ok" if last - NOW > datetime.timedelta(days=14) else "warn",
        f"последний пост {last:%d.%m}")
links = set()
for q in T["queues"]:
    fp = os.path.join(ROOT, q["file"])
    if os.path.exists(fp):
        for m in re.findall(r"bfep\.space(/[\w/.-]*)", open(fp, encoding="utf-8").read()): links.add(m or "/")
bad = [p for p in sorted(links) if fetch("https://bfep.space" + p)[0] != 200]
add("Автопостинг", f"Ссылки в текстах постов ({len(links)})", "fail" if bad else "ok", ", ".join(bad[:10]))

# 6. Робот публикаций и ключи (без публикации)
tok = os.environ.get("GH_TOKEN"); repo = os.environ.get("GITHUB_REPOSITORY")
if tok and repo:
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/autopost.yml/runs?per_page=5",
                                 headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"})
    try:
        runs = json.load(urllib.request.urlopen(req, timeout=30))["workflow_runs"]
        lastrun = ts(runs[0]["created_at"]) if runs else None
        fails = [r for r in runs if r.get("conclusion") == "failure"]
        st = "ok" if lastrun and NOW - lastrun < datetime.timedelta(hours=7) and len(fails) < 2 else "fail"
        add("Автопостинг", "Робот публикаций работает", st, f"последний запуск {lastrun:%d.%m %H:%M} UTC, сбоев из 5: {len(fails)}" if lastrun else "нет запусков")
    except Exception as e:
        add("Автопостинг", "Робот публикаций работает", "warn", e)
    # Скрипты публикации не падают и не повторяют посты (урок X 11–13.11: падение после публикации → 161 дубль)
    try:
        H = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"}
        done_runs = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://api.github.com/repos/{repo}/actions/workflows/autopost.yml/runs?status=completed&per_page=3", headers=H), timeout=30))["workflow_runs"]
        logs = ""
        for r in done_runs[:2]:
            jobs = json.load(urllib.request.urlopen(urllib.request.Request(r["jobs_url"], headers=H), timeout=30))["jobs"]
            for j in jobs:
                lp = subprocess.run(["gh", "api", f"repos/{repo}/actions/jobs/{j['id']}/logs"], capture_output=True, text=True, timeout=120)
                logs += lp.stdout
        tb = re.findall(r"File \"[^\"]*?(\w+_post\.py|post\.py|bot\.py)\"", logs)
        crashes = {}
        for f in tb: crashes[f] = crashes.get(f, 0) + 1
        ids = re.findall(r"опубликовано: (\S+)", logs)
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if logs:
            add("Автопостинг", "Скрипты публикации не падают", "fail" if crashes else "ok", ", ".join(f"{k}: {v} раз" for k, v in crashes.items()))
            add("Автопостинг", "Нет повторных публикаций", "fail" if dups else "ok", ", ".join(dups[:10]))
        else:
            add("Автопостинг", "Журналы робота прочитаны", "warn", "журналы последних запусков недоступны")
    except Exception as e:
        add("Автопостинг", "Журналы робота прочитаны", "warn", e)
if os.environ.get("TG_BOT_TOKEN"):
    c, _, b = fetch(f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}/getMe", body=True)
    add("Ключи", "Telegram-бот", "ok" if c == 200 else "fail", c)
if os.environ.get("DISCORD_WEBHOOK_URL"):
    c, _, _ = fetch(os.environ["DISCORD_WEBHOOK_URL"])
    add("Ключи", "Discord-вебхук", "ok" if c == 200 else "fail", c)
if os.environ.get("ONEUP_API_KEY"):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "oneup_post.py"), "--check"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    exp = "True" in re.sub(r"Категории.*", "", p.stdout, flags=re.S) or p.returncode
    add("Ключи", "OneUp (Snapchat)", "fail" if exp else "ok", "аккаунт отключён или ключ не принят" if exp else "")

# Итог
order = {"fail": 0, "warn": 1, "ok": 2}
R.sort(key=lambda r: (order[r["status"]], r["area"], r["name"]))
cnt = {s: sum(r["status"] == s for r in R) for s in order}
json.dump({"checked_at": NOW.isoformat(timespec="seconds"), "counts": cnt, "results": R},
          open(os.path.join(ROOT, "health", "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
icon = {"fail": "❌", "warn": "⚠️", "ok": "✅"}
md = [f"# Проверка связей {NOW:%Y-%m-%d %H:%M} UTC", f"❌ {cnt['fail']} · ⚠️ {cnt['warn']} · ✅ {cnt['ok']}", ""]
md += [f"- {icon[r['status']]} **{r['area']}** — {r['name']}" + (f": {r['detail']}" if r['detail'] else "") for r in R]
open(os.path.join(ROOT, "health", "report.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
print("\n".join(md))
