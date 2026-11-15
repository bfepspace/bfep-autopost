// Ежедневная проверка сайта глазами игрока с телефона (iPhone 13), все 6 языков. Ничего не отправляет в Brevo:
// запрос формы перехватывается и получает ответ «успех», проверяется только, В КАКУЮ форму (язык) он ушёл.
// Что проверяем на каждом языке:
//  1) Главная: переключатель языка, окно листа ожидания на этом языке, отправка уходит в форму Brevo этого языка
//     (= письмо придёт на этом языке), после отправки — «До скорой встречи» на этом языке.
//  2) Игры в браузере /play/<игра>/ (bfep, bluff, daily, sayit, kmg): выбор языка в игре, игра на этом языке,
//     автопрохождение кнопками до экрана итогов, звук (Web Audio / <audio>) звучит после нажатий, баннер подарка
//     на языке игры, окно почты над игрой на языке игры, отправка — в форму языка игры.
//  3) Приложение /app/ (BEEZOO Space): выбор языка, каждая карточка открывается без ошибок, игра в рамке — на языке хаба.
// Ошибки JS и ответы 4xx/5xx сайта пишутся у каждого шага. Итог: health/site-daily.json и health/site-daily.md.
// Запуск: node health/site-daily.js  (BASE=http://localhost:8765 для проверки локальной копии сайта)
const { chromium, devices } = require('playwright');
const fs = require('fs'), vm = require('vm');
const BASE = (process.env.BASE || 'https://bfep.space').replace(/\/$/, '');
const ONLY = (process.env.LANGS || 'en,de,es,ru,fr,zh').split(',');
const GAMES = (process.env.GAMES || 'bfep,bluff,daily,sayit,kmg').split(',');
const NATIVE = { en: 'English', de: 'Deutsch', es: 'Español', ru: 'Русский', fr: 'Français', zh: '中文' };
const HOMEBTN = { en: 'EN', de: 'DE', es: 'ES', ru: 'RU', fr: 'FR', zh: '中文' };
const HUBBTN = { en: 'EN', de: 'DE', es: 'ES', ru: 'RU', fr: 'FR', zh: 'ZH' };
const BANNER = { en: 'First 150 get a gift', de: 'Die ersten 150', es: 'Los primeros 150', ru: 'Первым 150', fr: 'Un cadeau pour les 150', zh: '前 150 名' };
const SKIP = /^(English|Deutsch|Español|Русский|Français|中文|EN|DE|ES|RU|FR|ZH|✕|×|←.*|.*bfep\.space.*|.*Install.*|📲.*|⚙️.*|🔇.*|🔊.*|.*Settings.*|.*How to play.*|📜.*)$/s;
const T0 = Date.now();

// Тексты и адреса форм берём с самого сайта (smart/waitlist.html), чтобы проверка не устаревала.
async function loadWaitlist(page) {
  const html = await (await page.request.get(BASE + '/smart/waitlist.html')).text();
  const forms = vm.runInNewContext('(' + html.match(/var FORMS\s*=\s*(\{[\s\S]*?\});/)[1] + ')');
  const T = vm.runInNewContext('(' + html.match(/var T\s*=\s*(\{[\s\S]*?\n\s*\});/)[1] + ')');
  const byUrl = {}; for (const [l, u] of Object.entries(forms)) byUrl[u.split('?')[0]] = l;
  return { forms, T, byUrl };
}

function soundHook() {
  window.__snd = 0;
  const bump = () => { window.__snd++; };
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) for (const m of ['createOscillator', 'createBufferSource']) {
      const o = AC.prototype[m]; AC.prototype[m] = function () { const n = o.apply(this, arguments); const s = n.start; n.start = function () { bump(); return s.apply(this, arguments); }; return n; };
    }
    const play = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () { if (!/^data:audio\/wav/.test(this.src || '')) bump(); return play.apply(this, arguments); };
    if (window.speechSynthesis) { const sp = speechSynthesis.speak.bind(speechSynthesis); speechSynthesis.speak = u => { bump(); try { return sp(u); } catch (e) {} }; }
  } catch (e) {}
}

async function ctx(b) {
  const c = await b.newContext({ ...devices['iPhone 13'], locale: 'en-US' });
  await c.addInitScript(soundHook);
  return c;
}
function watch(p, rec) {
  p.on('pageerror', e => rec.errors.push(e.message.slice(0, 140)));
  p.on('crash', () => rec.fail.push(`${rec.part}: вкладка упала (crash)`));
  p.on('response', r => { if (r.status() >= 400 && r.url().startsWith(BASE)) rec.bad.push(`${r.status()} ${r.url().replace(BASE, '')}`); });
}
// Перехват отправки в Brevo: ответ «успех», запоминаем язык формы
async function mockBrevo(c, wl, rec) {
  await c.route(/sibforms\.com/, route => {
    const u = route.request().url().split('?')[0];
    rec.sent.push(wl.byUrl[u] || 'unknown');
    route.fulfill({ status: 200, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: '{"success":true,"message":"ok"}' });
  });
}
async function fillWaitlist(root, wl, L, rec, label) {
  const t = wl.T[L];
  const box = root.locator('#waitlist').first();
  await box.scrollIntoViewIfNeeded().catch(() => {});
  const txt = (await box.innerText().catch(() => '')) || '';
  if (!txt.includes(t.title)) rec.fail.push(`${label}: окно почты не на языке ${L.toUpperCase()} (жду «${t.title}», вижу «${txt.split('\n')[0].slice(0, 60)}»)`);
  await box.locator('input[type=email]').fill(`qa-daily-${L}@example.com`);
  const cb = box.locator('.bfep-wl-consent input[type=checkbox]');
  if (await cb.count() && await cb.first().isVisible()) await cb.first().check().catch(() => {});
  const n0 = rec.sent.length;
  await box.locator('.bfep-wl-btn').click();
  await new Promise(r => setTimeout(r, 2500));
  const went = rec.sent.slice(n0);
  if (!went.length) rec.fail.push(`${label}: кнопка отправки не отправила форму`);
  else if (went[0] !== L) rec.fail.push(`${label}: почта ушла в форму ${String(went[0]).toUpperCase()} вместо ${L.toUpperCase()} → письмо придёт не на том языке`);
  const after = (await box.innerText().catch(() => '')) || '';
  if (went.length && !after.includes(t.dt)) rec.fail.push(`${label}: после отправки нет «${t.dt}» (вижу «${after.split('\n')[0].slice(0, 60)}»)`);
}

async function checkHome(b, wl, L) {
  const rec = { part: 'Главная', lang: L, errors: [], bad: [], fail: [], sent: [], notes: [] };
  const c = await ctx(b); await mockBrevo(c, wl, rec); const p = await c.newPage(); watch(p, rec);
  try {
    await p.goto(BASE + '/?s=qa-daily', { waitUntil: 'load', timeout: 45000 });
    await p.locator('#langs button', { hasText: HOMEBTN[L] }).first().click();
    await p.waitForTimeout(600);
    const hl = (await p.evaluate(() => document.documentElement.lang)).slice(0, 2);
    if (hl !== L) rec.fail.push(`Главная: после выбора ${L.toUpperCase()} язык страницы ${hl}`);
    await fillWaitlist(p, wl, L, rec, 'Главная, лист ожидания');
  } catch (e) { rec.fail.push('Главная: сбой проверки — ' + e.message.split('\n')[0].slice(0, 140)); }
  await c.close(); return rec;
}

async function checkGame(b, wl, g, L) {
  const rec = { part: `/play/${g}/`, lang: L, errors: [], bad: [], fail: [], sent: [], notes: [] };
  const c = await ctx(b); await mockBrevo(c, wl, rec); const p = await c.newPage(); watch(p, rec);
  try {
    await p.goto(BASE + `/play/${g}/?s=qa-daily`, { waitUntil: 'load', timeout: 45000 });
    await p.waitForTimeout(800);
    await p.locator('button:visible', { hasText: NATIVE[L] }).first().click({ timeout: 5000 });
    await p.waitForTimeout(500);
    const lang = await p.evaluate(() => typeof LANG !== 'undefined' ? LANG : null);
    if (lang !== L) rec.fail.push(`Игра ${g}: после выбора «${NATIVE[L]}» язык игры ${lang}`);
    // звук включён?
    const on = p.locator('button:visible', { hasText: '🔊' }).first();
    if (await on.count()) await on.click().catch(() => {});
    // следим за экранами
    await p.evaluate(() => { window.__scr = []; const o = window.show; window.show = function (s) { window.__scr.push(s); return o.apply(this, arguments); }; });
    // автопрохождение внутри страницы: до 80 нажатий, «главные» кнопки чаще
    const reached = await p.evaluate(async (skipSrc) => {
      const SKIP = new RegExp(skipSrc, 's'), wait = ms => new Promise(r => setTimeout(r, ms));
      const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !e.disabled; };
      for (let i = 0; i < 80; i++) {
        if ((window.__scr || []).some(s => s === 's-results' || s === 's-done')) return true;
        const cand = [...document.querySelectorAll('button, [role=button], .card, .opt')].filter(e => vis(e) && !SKIP.test((e.innerText || '').trim()) && !e.closest('#bfepGet,#bfepSheet'));
        if (!cand.length) { await wait(400); continue; }
        const main = cand.filter(e => /primary|big|main|go|next|start|play/i.test((e.className || '') + ' ' + (e.id || '')));
        const pick = main.length && Math.random() < 0.7 ? main[0] : cand[Math.floor(Math.random() * cand.length)];
        pick.click(); await wait(300);
      }
      return (window.__scr || []).some(s => s === 's-results' || s === 's-done');
    }, SKIP.source);
    const scr = await p.evaluate(() => [...new Set(window.__scr || [])]);
    const snd = await p.evaluate(() => window.__snd);
    if (!snd) rec.fail.push(`Игра ${g}: за ${scr.length} экранов не прозвучал ни один звук (звук включён)`);
    if (!reached) { rec.notes.push(`автопрохождение дошло до ${scr.slice(-1)[0] || 'старта'}, итоги открыты вручную`); await p.evaluate(() => show('s-results')).catch(e => rec.fail.push(`Игра ${g}: экран итогов не открылся — ${e.message.slice(0, 80)}`)); }
    rec.notes.push(`экраны: ${scr.join(' → ') || '—'}; звуков: ${snd}`);
    const ban = p.locator('#bfepGet');
    await ban.waitFor({ timeout: 4000 }).catch(() => {});
    if (!(await ban.count())) rec.fail.push(`Игра ${g}: на итогах нет баннера «подарок первым 150»`);
    else {
      const bt = await ban.innerText();
      if (!bt.includes(BANNER[L])) rec.fail.push(`Игра ${g}: баннер не на языке ${L.toUpperCase()} («${bt.slice(0, 60)}»)`);
      await ban.locator('a').click();
      await p.locator('#bfepSheet #waitlist').waitFor({ timeout: 6000 }).catch(() => rec.fail.push(`Игра ${g}: окно почты над игрой не открылось`));
      if (await p.locator('#bfepSheet #waitlist').count()) await fillWaitlist(p.locator('#bfepSheet').page(), wl, L, rec, `Игра ${g}, окно почты`);
    }
  } catch (e) { rec.fail.push(`Игра ${g}: сбой проверки — ` + e.message.split('\n')[0].slice(0, 140)); }
  await c.close(); return rec;
}

async function checkHub(b, L) {
  const rec = { part: '/app/ (BEEZOO Space)', lang: L, errors: [], bad: [], fail: [], sent: [], notes: [] };
  const c = await ctx(b); const p = await c.newPage(); watch(p, rec);
  try {
    await p.goto(BASE + '/app/?s=qa-daily', { waitUntil: 'load', timeout: 45000 });
    await p.waitForTimeout(800);
    await p.locator('button:visible', { hasText: new RegExp('^' + HUBBTN[L] + '$') }).first().click({ timeout: 5000 });
    await p.waitForTimeout(400);
    const hl = (await p.evaluate(() => document.documentElement.lang)).slice(0, 2);
    if (hl !== L) rec.fail.push(`Приложение: после выбора ${HUBBTN[L]} язык ${hl}`);
    const n = await p.locator('#s-home button:visible').count();
    let opened = 0;
    for (let i = 0; i < n; i++) {
      await p.goto(BASE + '/app/?s=qa-daily', { waitUntil: 'load', timeout: 45000 }); await p.waitForTimeout(500);
      const btn = p.locator('#s-home button:visible').nth(i);
      const name = ((await btn.innerText().catch(() => '')) || '').split('\n')[0].trim();
      if (!name || SKIP.test(name) || /^✨|Beezoo|Install/i.test(name)) continue;
      const e0 = rec.errors.length;
      await btn.click({ timeout: 3000 }).catch(() => {});
      await p.waitForTimeout(1500);
      const fr = p.frames().find(f => /\/app\/games\//.test(f.url()));
      if (fr) {
        const fl = await fr.evaluate(() => typeof LANG !== 'undefined' ? LANG : (window.ST && ST.lang) || null).catch(() => null);
        if (fl && fl !== L) rec.fail.push(`Приложение, «${name}»: игра открылась на ${fl}, а выбран ${L}`);
        const empty = await fr.evaluate(() => document.body.innerText.trim().length < 20).catch(() => true);
        if (empty) rec.fail.push(`Приложение, «${name}»: пустой экран`);
      }
      if (rec.errors.length > e0) rec.fail.push(`Приложение, «${name}»: ошибка JS — ${rec.errors[e0]}`);
      opened++;
    }
    rec.notes.push(`открыто карточек: ${opened}`);
  } catch (e) { rec.fail.push('Приложение: сбой проверки — ' + e.message.split('\n')[0].slice(0, 140)); }
  await c.close(); return rec;
}

function limit(pr, part, lang, secs = 150) {
  return Promise.race([pr, new Promise(r => setTimeout(() => r({ part, lang, errors: [], bad: [], sent: [], notes: [], fail: [`${part}: проверка зависла дольше ${secs} с`] }), secs * 1000))]);
}
(async () => {
  const b = await chromium.launch();
  const c0 = await b.newContext(); const wl = await loadWaitlist(await c0.newPage()); await c0.close();
  const out = [];
  for (const L of ONLY) {
    out.push(await limit(checkHome(b, wl, L), 'Главная', L));
    for (const g of GAMES) out.push(await limit(checkGame(b, wl, g, L), `/play/${g}/`, L));
    if (!process.env.NOHUB) out.push(await limit(checkHub(b, L), '/app/ (BEEZOO Space)', L, 400));
  }
  await b.close();
  for (const r of out) { r.errors = [...new Set(r.errors)].slice(0, 5); r.bad = [...new Set(r.bad)].slice(0, 5); for (const e of r.errors) if (!r.fail.some(f => f.includes(e))) r.fail.push(`${r.part}: ошибка JS — ${e}`); for (const x of r.bad) r.fail.push(`${r.part}: не загрузилось ${x}`); }
  const fails = out.filter(r => r.fail.length);
  const res = { at: new Date().toISOString(), base: BASE, secs: Math.round((Date.now() - T0) / 1000), checks: out.length, failed: fails.length, ok: !fails.length, results: out };
  fs.writeFileSync(__dirname + '/site-daily.json', JSON.stringify(res, null, 1));
  const md = [`# Ежедневная проверка сайта ${res.at.slice(0, 16).replace('T', ' ')} UTC`, '', fails.length ? `❌ Найдено проблем: ${fails.reduce((a, r) => a + r.fail.length, 0)} в ${fails.length} из ${out.length} проверок` : `✅ Всё работает: ${out.length} проверок (6 языков × главная, 5 игр, приложение)`, ''];
  for (const r of fails) { md.push(`## ${r.part} — ${r.lang.toUpperCase()}`); r.fail.forEach(f => md.push('- ' + f)); md.push(''); }
  md.push('## Подробно'); for (const r of out) md.push(`- ${r.fail.length ? '❌' : '✅'} ${r.part} ${r.lang.toUpperCase()}${r.notes.length ? ' — ' + r.notes.join('; ') : ''}`);
  fs.writeFileSync(__dirname + '/site-daily.md', md.join('\n') + '\n');
  console.log(md.slice(0, 3).join('\n'), `(${res.secs} с)`);
})();
