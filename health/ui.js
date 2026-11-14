// Как сайт выглядит и работает у посетителя с телефона (iPhone): ошибки JS, горизонтальная прокрутка,
// где форма записи, сколько грузится, старые названия бренда. Пишет health/ui.json. Ничего не отправляет в формы.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const BASE = 'https://bfep.space';
const games = ['bfep', 'bluff', 'daily', 'sayit', 'kmg'];
const pages = [
  { path: '/?s=tt-bio-all', name: 'Главная (гость из TikTok)', waitlist: true },
  { path: '/', name: 'Главная (без метки)', waitlist: true },
  { path: '/app/', name: 'Приложение в браузере' },
  ...games.map(g => ({ path: `/play/${g}/`, name: `Игра /play/${g}/` })),
  ...games.map(g => ({ path: `/${g}/`, name: `Умная ссылка /${g}/` })),
];
const OLD = /Bomi|Best Fun Evening(?! Games FZE)/;
(async () => {
  const b = await chromium.launch();
  const out = [];
  for (const lang of ['en', 'ru']) {
    for (const pg of pages) {
      if (lang === 'ru' && !pg.waitlist) continue;
      const c = await b.newContext({ ...devices['iPhone 13'], locale: lang });
      const p = await c.newPage();
      const errs = [], bad = [];
      p.on('pageerror', e => errs.push(e.message.slice(0, 120)));
      p.on('response', r => { if (r.status() >= 400 && r.url().startsWith(BASE)) bad.push(`${r.status()} ${r.url().replace(BASE, '')}`); });
      const t0 = Date.now();
      let ok = true;
      try { await p.goto(BASE + pg.path, { waitUntil: 'load', timeout: 45000 }); } catch (e) { ok = false; errs.push('не загрузилась: ' + e.message.slice(0, 80)); }
      const loadMs = Date.now() - t0;
      await p.waitForTimeout(2500);
      const d = ok ? await p.evaluate(() => {
        const wl = document.getElementById('waitlist');
        return {
          overflow: document.documentElement.scrollWidth - window.innerWidth,
          screens: wl ? +(wl.getBoundingClientRect().top / window.innerHeight + scrollY / window.innerHeight).toFixed(1) : null,
          wlVisible: wl ? getComputedStyle(wl).display !== 'none' : false,
          text: document.body.innerText.slice(0, 20000),
          empty: document.body.innerText.trim().length < 40,
        };
      }) : {};
      out.push({ lang, path: pg.path, name: pg.name, loadMs, errors: errs, bad: [...new Set(bad)].slice(0, 5),
        overflow: d.overflow || 0, waitlistScreens: pg.waitlist ? d.screens : undefined, waitlistVisible: pg.waitlist ? d.wlVisible : undefined,
        oldBrand: d.text ? (d.text.match(OLD) || [null])[0] : null, empty: !!d.empty });
      await c.close();
    }
  }
  await b.close();
  fs.writeFileSync(__dirname + '/ui.json', JSON.stringify(out, null, 1));
  console.log(JSON.stringify(out.map(o => [o.lang, o.path, o.loadMs, o.errors.length, o.overflow, o.waitlistScreens, o.oldBrand])));
})();
