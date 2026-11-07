#!/usr/bin/env python3
"""Модуль «Свежее» — собрать опубликованную колоду fresh/current.json из одобренных колод.
   python3 fresh/tools/fresh_build.py [--today 2026-11-07] [--studio <папка studio>]
   Берёт fresh/decks/*.json со status "approved", выкидывает просроченные карточки,
   новые — первыми, не больше 40 карточек. Для «Загадки дня» раздаёт по одной свежей
   загадке на день (поле daily), начиная с today. С --studio кладёт встроенную копию
   в <studio>/games/fresh/deck.js (на случай, если телефон без интернета)."""
import json, sys, datetime, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fresh_check import check

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_ITEMS = 40

def main():
    a = sys.argv
    today = datetime.date.fromisoformat(a[a.index('--today') + 1]) if '--today' in a else datetime.date.today()
    items, decks = [], []
    for p in sorted((ROOT / 'decks').glob('*.json')):
        deck = json.loads(p.read_text(encoding='utf-8'))
        if deck.get('status') != 'approved': continue
        errs = check(deck)
        if errs: print('❌', p.name, *errs, sep='\n  '); sys.exit(1)
        decks.append(deck['deck'])
        items += [it for it in deck['items'] if datetime.date.fromisoformat(it['expires']) >= today]
    seen, uniq = set(), []
    for it in sorted(items, key=lambda i: (i['from'], i['id']), reverse=True):
        if it['id'] in seen: continue
        seen.add(it['id']); uniq.append(it)
    uniq = uniq[:MAX_ITEMS]
    # «Загадка дня»: одна свежая на день, самые новые — раньше; уже назначенные дни в прошлом не трогаем
    day = today
    for it in uniq:
        if it.get('age', 0) != 0: continue
        if it.get('daily') and datetime.date.fromisoformat(it['daily']) < today: continue
        while day < datetime.date.fromisoformat(it['from']): day += datetime.timedelta(days=1)
        if day > datetime.date.fromisoformat(it['expires']): continue
        it['daily'] = day.isoformat(); day += datetime.timedelta(days=1)
    out = {'v': 1, 'deck': 'current', 'published': today.isoformat(), 'built_from': decks, 'items': uniq}
    (ROOT / 'current.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'✅ fresh/current.json: {len(uniq)} карточек из {len(decks)} колод, свежие загадки дня до {(day - datetime.timedelta(days=1)).isoformat()}')
    if '--studio' in a:
        st = pathlib.Path(a[a.index('--studio') + 1]) / 'games' / 'fresh' / 'deck.js'
        st.parent.mkdir(parents=True, exist_ok=True)
        st.write_text('/* Встроенная свежая колода (fresh/current.json из bfep-autopost). Собирает fresh/tools/fresh_build.py. */\n'
                      'var FRESH_DECK = ' + json.dumps(out, ensure_ascii=False) + ';\n', encoding='utf-8')
        print('✅', st)

if __name__ == '__main__': main()
