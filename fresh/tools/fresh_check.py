#!/usr/bin/env python3
"""Модуль «Свежее» — проверка колоды перед публикацией.
   python3 fresh/tools/fresh_check.py fresh/decks/fresh-2026-11-07.json [--today 2026-11-07]
   Выход 0 — колода годна; иначе печатает каждую ошибку и выходит с 1.
   Проверяет: формат, 6 языков, даты и срок годности, ≥2 источника с разных сайтов,
   стоп-слова (политика, трагедии, страшное), чужие торговые марки, возраст, длину,
   что подсказка не выдаёт ответ, что нет HTML."""
import json, sys, re, datetime, pathlib
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
LANGS = ['en', 'ru', 'de', 'es', 'fr', 'zh']
CATS = ['space', 'science', 'engineering', 'tech', 'nature', 'records', 'sport', 'culture', 'local']
MAX_LIFE = 60          # дней — дольше «свежим» не бывает
MAX_SOURCE_AGE = 21    # дней между новостью и попаданием в колоду
MIN_CLUES = 7

def d(s): return datetime.date.fromisoformat(s)

def norm(s): return re.sub(r'\s+', ' ', re.sub(r"[’'`´\-.,!?:;«»\"()]", ' ', s.lower().replace('ё', 'е'))).strip()

def words_hit(text, words, allow):
    t = ' ' + norm(text) + ' '
    out = []
    for w in words:
        if w in allow: continue
        nw = norm(w)
        if not nw: continue
        # латиница — целым словом; кириллица — по основе (начало слова)
        if re.search(r'[a-z]', nw):
            if re.search(r'(?<![a-z0-9])' + re.escape(nw) + r'(?![a-z0-9])', t): out.append(w)
        elif (' ' + nw) in t: out.append(w)
    return out

def check(deck, today=None):
    stop = json.loads((ROOT / 'stoplist.json').read_text(encoding='utf-8'))
    E = []
    if deck.get('v') != 1: E.append('v должен быть 1')
    for k in ('deck', 'published', 'items'):
        if k not in deck: E.append(f'нет поля {k}')
    if E: return E
    pub = d(deck['published'])
    ids = set()
    for n, it in enumerate(deck['items'], 1):
        p = f"#{n} {it.get('id', '?')}:"
        for k in ('id', 'cat', 'age', 'emoji', 'from', 'expires', 'answer', 'clues', 'fact', 'sources', 'checked'):
            if k not in it: E.append(f'{p} нет поля {k}')
        if any(k not in it for k in ('id', 'answer', 'clues', 'fact', 'sources', 'from', 'expires')): continue
        if it['id'] in ids: E.append(f'{p} повтор id')
        ids.add(it['id'])
        if it.get('cat') not in CATS: E.append(f'{p} cat не из списка {CATS}')
        if it.get('age') not in (0, 1): E.append(f'{p} age: 0 = всем (6+), 1 = 12+')
        try:
            f, x = d(it['from']), d(it['expires'])
            if x <= f: E.append(f'{p} expires раньше from')
            if (x - f).days > MAX_LIFE: E.append(f'{p} срок годности больше {MAX_LIFE} дней')
            if today and x < today: E.append(f'{p} уже просрочена ({it["expires"]})')
            if it.get('daily') and not (f <= d(it['daily']) <= x): E.append(f'{p} daily вне from…expires')
        except Exception as e: E.append(f'{p} дата: {e}')
        # источники
        src = it['sources']
        doms = {urlparse(s.get('url', '')).netloc.lower().removeprefix('www.') for s in src}
        if len(src) < 2 or len(doms) < 2: E.append(f'{p} нужно ≥2 источника с разных сайтов')
        for s in src:
            if not s.get('url', '').startswith('https://'): E.append(f'{p} источник без https: {s.get("url")}')
            if not s.get('date'): E.append(f'{p} у источника нет даты')
            else:
                try:
                    age = (d(it['from']) - d(s['date'])).days
                    if age > MAX_SOURCE_AGE: E.append(f'{p} новость старше {MAX_SOURCE_AGE} дней ({s["date"]})')
                except Exception as e: E.append(f'{p} дата источника: {e}')
        # языки и тексты
        allow = set(it.get('allow', []))
        en_clues = it['clues'].get('en', [])
        if len(en_clues) < MIN_CLUES: E.append(f'{p} нужно ≥{MIN_CLUES} подсказок')
        for c in en_clues:
            if ' ' not in c or re.match(r'^[A-Za-z]', c): E.append(f'{p} EN-подсказка должна начинаться с эмодзи и пробела: «{c}»')
        for L in LANGS:
            a = it['answer'].get(L); cl = it['clues'].get(L); fa = it['fact'].get(L)
            if not a or not cl or not fa: E.append(f'{p} нет языка {L}'); continue
            if len(cl) != len(en_clues): E.append(f'{p} {L}: подсказок {len(cl)}, а в EN {len(en_clues)}')
            if len(a) > 32: E.append(f'{p} {L}: ответ длиннее 32 знаков')
            if len(fa) > 170: E.append(f'{p} {L}: факт длиннее 170 знаков')
            labels = [c[c.index(' ') + 1:] if L == 'en' else c for c in cl]
            for lb in labels:
                if len(lb) > 42: E.append(f'{p} {L}: подсказка длиннее 42 знаков: «{lb}»')
                # подсказка не выдаёт ответ (любое слово ответа от 4 букв)
                for w in norm(a).split():
                    if len(w) >= 4 and w in norm(lb): E.append(f'{p} {L}: подсказка выдаёт ответ: «{lb}»')
            blob = ' '.join([a, fa] + labels)
            if re.search(r'[<>{}]|https?://', blob): E.append(f'{p} {L}: HTML/ссылки в тексте запрещены')
            hit = words_hit(blob, stop['topics'], allow)
            if hit: E.append(f'{p} {L}: запрещённая тема: {", ".join(hit)}')
            hit = words_hit(' '.join([a] + labels), stop['marks'], allow)
            if hit: E.append(f'{p} {L}: чужая торговая марка: {", ".join(hit)}')
        if 'wyr' in it:
            for L in LANGS:
                w = it['wyr'].get(L)
                if not (isinstance(w, list) and len(w) == 2): E.append(f'{p} wyr {L}: нужны два варианта')
                else:
                    hit = words_hit(' '.join(w), stop['topics'] + stop['marks'], allow)
                    if hit: E.append(f'{p} wyr {L}: {", ".join(hit)}')
        if allow and not it.get('note'): E.append(f'{p} allow без пояснения note')
    return E

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    today = None
    if '--today' in sys.argv: today = d(sys.argv[sys.argv.index('--today') + 1]); args = [a for a in args if a != str(today)]
    bad = 0
    for path in args:
        deck = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
        errs = check(deck, today)
        print(('✅ ' if not errs else '❌ ') + path + f' — карточек {len(deck.get("items", []))}, ошибок {len(errs)}')
        for e in errs: print('   ', e)
        bad += bool(errs)
    sys.exit(1 if bad else 0)
