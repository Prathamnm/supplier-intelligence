// Browser smoke test: open the built site in headless Chrome/Edge, click
// through every page in the menu like a user, and fail on any JS error or
// blank page. Pages opened directly can work while in-app navigation
// breaks (effect cleanups only run on navigation), so this clicks.
//
//   npm run build && npm run smoke            (CHROME=/path/to/chrome to override)
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const PAGES = ['Untraced returns', 'Briefs', 'Method', 'Upload', 'Overview']
const CANDIDATES = [
  process.env.CHROME,
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]
const browserPath = CANDIDATES.find((p) => p && existsSync(p))
if (!browserPath) throw new Error('No Chrome/Edge found; set CHROME=/path/to/browser')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const sitePort = 4300 + Math.floor(Math.random() * 500)
const debugPort = 9300 + Math.floor(Math.random() * 500)
const site = spawn('npx', ['vite', 'preview', '--port', String(sitePort), '--strictPort'], { shell: true })
const browser = spawn(browserPath, [
  '--headless=new', '--no-sandbox', '--disable-gpu', `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'smoke-'))}`, 'about:blank',
])
const stop = (code) => { browser.kill(); site.kill(); process.exit(code) }

async function waitFor(url) {
  for (let i = 0; i < 80; i++) {
    try { const r = await fetch(url); if (r.ok) return r } catch { /* not up yet */ }
    await sleep(250)
  }
  throw new Error(`timed out waiting for ${url}`)
}

try {
  await waitFor(`http://localhost:${sitePort}/`)
  const targets = await (await waitFor(`http://127.0.0.1:${debugPort}/json`)).json()
  const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))

  let id = 0
  const pending = new Map()
  const errors = []
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data)
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id) }
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text)
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map((a) => a.value ?? a.description).join(' '))
  })
  const send = (method, params = {}) => new Promise((r) => { const n = ++id; pending.set(n, r); ws.send(JSON.stringify({ id: n, method, params })) })
  const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true })).result?.value

  await send('Runtime.enable')
  await send('Page.navigate', { url: `http://localhost:${sitePort}/#/` })
  await sleep(3000)

  let failed = false
  const check = async (label) => {
    const text = await evaluate('document.querySelector("main")?.innerText.trim().length ?? 0')
    const ok = errors.length === 0 && text > 100
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label.padEnd(18)} ${text} chars${errors.length ? `  errors: ${errors.join(' | ').slice(0, 300)}` : ''}`)
    failed ||= !ok
    errors.length = 0
  }
  await check('Overview (load)')
  for (const label of PAGES) {
    await evaluate(`[...document.querySelectorAll('nav a')].find(a => a.textContent.trim() === ${JSON.stringify(label)})?.click()`)
    await sleep(1500)
    await check(label)
  }
  await evaluate(`document.querySelector('a[href*="supplier/"]')?.click()`)
  await sleep(1500)
  await check('A supplier page')
  stop(failed ? 1 : 0)
} catch (e) {
  console.error(e)
  stop(1)
}
