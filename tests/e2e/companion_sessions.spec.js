/*
 * companion.html 跨会话记忆 E2E（Phase 15 Task 3）
 *
 * 覆盖五项：
 *   A 上次对话卡注入系统提示（格式逐字）
 *   B 第四检索源 Tier-2 标签（命中对话者自述）
 *   C 本次不记开关（exclude_session 事件 + 提示条 + 后续轮次带 exclude）+ viewer 字段
 *   D 第四检索源 Tier-3 标签（命中她的回复）+ recent_dates 为空时省略「更早还有」
 *   E sessions 文件 404 时完全降级（无卡、无标签、无额外报错）
 *
 * 运行前提：
 *   1. 本机 :8020 提供 people/<person>/archive_out（python -m http.server 8020）
 *   2. 已安装 playwright：npm i playwright（仓库当前未安装，见下）
 *
 * 运行：node tests/e2e/companion_sessions.spec.js
 *
 * 注意（2026-09-07 记录）：本脚本首次验收时仓库与全局均无 playwright 包，
 * 实际是通过 Playwright MCP 逐条执行等价断言完成的，五项全绿。
 * 脚本入库是为了可复跑与二十年后仍可读，但它本身尚未在 node 下跑过。
 */
'use strict';

const { chromium } = require('playwright');

const BASE = process.env.COMPANION_URL || 'http://127.0.0.1:8020/companion.html';
const STORAGE_KEY = process.env.COMPANION_STORAGE_KEY || 'companion_mama_byok';
const LLM_URL = 'https://mock.llm/v1/chat/completions';

const SSE = 'data: {"choices":[{"delta":{"content":"侬好"}}]}\n\ndata: [DONE]\n\n';

function pad2(n) { return String(n).padStart(2, '0'); }

function yesterday() {
  const d = new Date(Date.now() - 86400000);
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
}

function sessionsFixture(opts) {
  const yst = opts.date;
  return JSON.stringify({
    schema_version: 1, person: 'mama', epoch: 2, viewer: 'owner',
    tier_policy: { user: 2, simulacrum: 3 },
    source_stats: { files: 1, records: 4, bad_lines: 0, excluded_sessions: 0, redacted_turns: 0, sessions_kept: 1 },
    last_card: {
      session_id: '20260101-000000-OLDSES', date: yst,
      started_at: yst + 'T20:00:00+08:00', ended_at: yst + 'T20:10:00+08:00', turns: 4,
      user_lines: opts.userLines, user_lines_truncated: false,
      last_exchange: opts.lastExchange
    },
    recent_dates: opts.recentDates,
    sessions: [{ session_id: '20260101-000000-OLDSES', date: yst, turns: opts.turns }]
  });
}

async function setupRoutes(page, sink, sessionsBody) {
  await page.unrouteAll();
  const json = (obj) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(obj) });
  await page.route('**/data/chat_context.json', r => r.fulfill(json({ system_prompt: 'SYSPROMPT_BASE', message_shards: [] })));
  await page.route('**/data/memories.json', r => r.fulfill(json({ entries: [] })));
  await page.route('**/data/transcripts.json', r => r.fulfill(json({ entries: [] })));
  await page.route('**/data/avatar/emotions.json', r => r.fulfill({ status: 404, body: '' }));
  await page.route('**/sessions_data/owner/sessions.json', r =>
    sessionsBody ? r.fulfill({ status: 200, contentType: 'application/json', body: sessionsBody })
                 : r.fulfill({ status: 404, body: '' }));
  await page.route('**/health', r => r.fulfill(json({ status: 'ok' })));
  await page.route('**/session', async r => {
    try { sink.sessionPosts.push(JSON.parse(r.request().postData() || '{}')); } catch (e) { /* ignore */ }
    await r.fulfill(json({ ok: true }));
  });
  await page.route('**/tts', r => r.fulfill({ status: 503, body: '' }));
  await page.route('https://mock.llm/**', async r => {
    try { sink.llmRequests.push(JSON.parse(r.request().postData() || '{}')); } catch (e) { /* ignore */ }
    await r.fulfill({ status: 200, contentType: 'text/event-stream', body: SSE });
  });
}

async function send(page, text, waitMs) {
  await page.fill('#input-text', text);
  await page.click('#send-btn');
  await page.waitForTimeout(waitMs || 2200);
}

function lastMessages(sink) {
  const first = sink.llmRequests[0] || {};
  const msgs = first.messages || [];
  return {
    system: (msgs[0] && msgs[0].content) || '',
    user: (msgs[msgs.length - 1] && msgs[msgs.length - 1].content) || ''
  };
}

const results = [];
function check(name, cond, detail) {
  results.push({ name, ok: !!cond, detail: detail || '' });
  console.log((cond ? 'PASS  ' : 'FAIL  ') + name + (cond ? '' : '  <- ' + (detail || '')));
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 900, height: 1400 } });
  await context.addInitScript((key, url) => {
    localStorage.setItem(key, JSON.stringify({
      provider: 'custom', url: url, model: 'm', key: 'k',
      profiles: { custom: { url: url, model: 'm', key: 'k' } }
    }));
  }, STORAGE_KEY, LLM_URL);
  const page = await context.newPage();
  const yst = yesterday();

  // ---------- A/B/C：完整夹具 ----------
  const sinkABC = { llmRequests: [], sessionPosts: [] };
  await setupRoutes(page, sinkABC, sessionsFixture({
    date: yst,
    userLines: ['我昨天去看了外婆', '筒骨汤真好喝'],
    lastExchange: { user: '筒骨汤真好喝', simulacrum: '多穿点衣裳' },
    recentDates: ['2026-08-30', '2026-08-28'],
    turns: [
      { turn: 1, role: 'user', text: '筒骨汤真好喝', ts: yst + 'T20:00:00+08:00' },
      { turn: 1, role: 'simulacrum', text: '多穿点衣裳侬', ts: yst + 'T20:00:30+08:00' }
    ]
  }));
  await page.goto(BASE);
  await page.waitForTimeout(2000);
  await send(page, '筒骨汤', 2500);

  const abc = lastMessages(sinkABC);
  check('A1 卡片注入系统提示', abc.system.indexOf('【往次对话 · 第二纪元 · 非她生前记忆】') >= 0, abc.system.slice(0, 120));
  check('A2 原系统提示在前', abc.system.indexOf('SYSPROMPT_BASE') === 0);
  check('A3 天数为「1 天前」', abc.system.indexOf('1 天前') >= 0);
  check('A4 含对话者当时说过的话', abc.system.indexOf('我昨天去看了外婆') >= 0);
  check('A5 含最后一来一回', abc.system.indexOf('最后一来一回') >= 0);
  check('A6 含更早日期', abc.system.indexOf('更早还有') >= 0);
  check('B1 检索块含 Tier-2 标签', abc.user.indexOf('[对话者自述 · 往次对话 Tier-2]') >= 0, abc.user.slice(0, 160));

  const before = sinkABC.sessionPosts.length;
  await page.evaluate(() => {
    const cb = document.getElementById('cfg-no-memory');
    cb.checked = true;
    cb.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.waitForTimeout(1000);
  const bannerVisible = await page.evaluate(() => {
    const b = document.getElementById('no-memory-banner');
    return !!b && !b.hidden && getComputedStyle(b).display !== 'none';
  });
  const posted = sinkABC.sessionPosts.slice(before);
  check('C1 所有会话记录带 viewer=owner', sinkABC.sessionPosts.length > 0 && sinkABC.sessionPosts.every(r => r.viewer === 'owner'));
  check('C2 勾选后发出 exclude_session 事件', posted.some(r => r.role === 'event' && r.text === 'exclude_session' && r.exclude === true));
  check('C3 提示条可见', bannerVisible);

  await send(page, '第二句', 2000);
  const afterToggle = sinkABC.sessionPosts.slice(before).filter(r => r.role === 'user');
  check('C4 勾选后的轮次带 exclude', afterToggle.length > 0 && afterToggle.every(r => r.exclude === true));

  // ---------- D：命中她的回复 + recent_dates 为空 ----------
  const sinkD = { llmRequests: [], sessionPosts: [] };
  await setupRoutes(page, sinkD, sessionsFixture({
    date: yst,
    userLines: ['我昨天去看了外婆'],
    lastExchange: { user: '我昨天去看了外婆', simulacrum: '外婆身体好伐' },
    recentDates: [],
    turns: [
      { turn: 1, role: 'user', text: '我昨天去看了外婆', ts: yst + 'T20:00:00+08:00' },
      { turn: 1, role: 'simulacrum', text: '外婆身体好伐要多穿点', ts: yst + 'T20:00:30+08:00' }
    ]
  }));
  await page.goto(BASE);
  await page.waitForTimeout(1800);
  await send(page, '外婆');
  const dd = lastMessages(sinkD);
  check('D1 检索块含 Tier-3 标签', dd.user.indexOf('[往次数字对话 Tier-3]') >= 0, dd.user.slice(0, 200));
  check('D2 Tier-2 排在 Tier-3 之前', dd.user.indexOf('[对话者自述 · 往次对话 Tier-2]') >= 0 &&
        dd.user.indexOf('[对话者自述 · 往次对话 Tier-2]') < dd.user.indexOf('[往次数字对话 Tier-3]'));
  check('D3 recent_dates 为空时省略「更早还有」', dd.system.indexOf('更早还有') < 0);

  // ---------- E：sessions 404 降级 ----------
  const sinkE = { llmRequests: [], sessionPosts: [] };
  const hardErrors = [];
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const t = m.text();
    if (t.indexOf('503') >= 0 || t.indexOf('404') >= 0) return;   // 预期内：tts 与 emotions
    hardErrors.push(t);
  });
  await setupRoutes(page, sinkE, null);
  await page.goto(BASE);
  await page.waitForTimeout(1800);
  await send(page, '外婆');
  const ee = lastMessages(sinkE);
  check('E1 系统提示只剩原文', ee.system === 'SYSPROMPT_BASE', ee.system.slice(0, 120));
  check('E2 无卡片', ee.system.indexOf('【往次对话') < 0);
  check('E3 无第二纪元标签', ee.user.indexOf('Tier-2]') < 0 && ee.user.indexOf('Tier-3]') < 0);
  check('E4 无额外控制台报错', hardErrors.length === 0, hardErrors.join(' | '));

  await browser.close();

  const failed = results.filter(r => !r.ok);
  console.log('\n' + (results.length - failed.length) + '/' + results.length + ' passed');
  process.exit(failed.length ? 1 : 0);
})().catch(err => { console.error(err); process.exit(1); });
