"""Проверка PR перед автоматическим merge.

Ошибка (PR не сливается): битый JSON, синтаксис Python, повтор id,
неверное время at_utc, локальный файл ролика не найден.
Предупреждение (не мешает merge): медиа-ссылка raw.githubusercontent
указывает на путь, которого нет в репозитории.
"""
import glob
import json
import os
import py_compile
import re
import sys
from datetime import datetime

errors, warnings = [], []

data = {}
for f in sorted(glob.glob("*.json")) + sorted(glob.glob("health/*.json")):
    try:
        with open(f, encoding="utf-8") as fh:
            data[f] = json.load(fh)
    except Exception as e:  # noqa: BLE001
        errors.append(f"{f}: JSON не читается: {e}")

for f in sorted(glob.glob("*.py")) + sorted(glob.glob("health/*.py")):
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        errors.append(f"{f}: ошибка синтаксиса Python: {e.msg}")

RAW = re.compile(r"https://raw\.githubusercontent\.com/bfepspace/bfep-autopost/[^/]+/(.+)$")

for f in ("schedule.json", "x.json", "discord.json", "snap.json"):
    items = data.get(f)
    if not isinstance(items, list):
        if f in data:
            errors.append(f"{f}: ожидался список постов")
        continue
    seen = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errors.append(f"{f}[{i}]: пост не объект")
            continue
        pid = it.get("id", f"#{i}")
        if pid in seen:
            errors.append(f"{f}: id повторяется: {pid}")
        seen.add(pid)
        at = it.get("at_utc")
        if not at:
            errors.append(f"{f}: {pid}: нет at_utc")
        else:
            try:
                datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                errors.append(f"{f}: {pid}: неверное at_utc {at!r} (нужно ГГГГ-ММ-ДДTЧЧ:ММ:ССZ)")
        local = it.get("file")
        if local and not os.path.exists(local):
            errors.append(f"{f}: {pid}: нет файла {local}")
        media = it.get("media")
        for m in media if isinstance(media, list) else [media]:
            if isinstance(m, str):
                mm = RAW.match(m)
                if mm and not os.path.exists(mm.group(1)):
                    warnings.append(f"{f}: {pid}: в репозитории нет {mm.group(1)}")

for w in warnings:
    print("ПРЕДУПРЕЖДЕНИЕ:", w)
for e in errors:
    print("ОШИБКА:", e)
print(f"Итого: ошибок {len(errors)}, предупреждений {len(warnings)}")
sys.exit(1 if errors else 0)
