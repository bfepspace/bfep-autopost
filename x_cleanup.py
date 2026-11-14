"""Удаляет дубли постов в X из x_dups.json (сбой робота 11–13.11: один пост выходил каждые 5 минут).
Запуск только вручную (workflow x-cleanup). Удалённые id убираются из файла."""
import json, sys, time
src = open("x_post.py", encoding="utf-8").read()
exec(src.split('if "--check" in sys.argv')[0])  # ключи, подпись OAuth, call()

ids = json.load(open("x_dups.json"))
left = []
for i, t in enumerate(ids):
    try:
        r = call("DELETE", f"/tweets/{t}")
        print("удалён", t, r.get("data"))
    except Exception as e:
        print("не удалён", t, e); left.append(t)
        if " 429" in str(e) or " 402" in str(e): left += ids[i + 1:]; break  # 402: кредиты кончились — не перебирать остальные
    time.sleep(1)
json.dump(left, open("x_dups.json", "w"))
print("осталось", len(left))
