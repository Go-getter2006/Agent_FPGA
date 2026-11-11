// 阶段 3 验收：一名学生从登录走完一道创作题的全部步骤；每一步都有事件日志；关键页面截图与原型布局一致
import { expect, test, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

const ROOT = resolve(HERE, '../..')
const PASSWORD = process.env.DEMO_PASSWORD ?? 'e2e-pass-123'
const E2E_DB = `${process.env.E2E_DIR ?? '/tmp/agent_fpga_e2e'}/e2e.db`
const SHOTS = resolve(HERE, 'screenshots')
const PID = 'seq_detector_101'

const read = (p: string) => readFileSync(resolve(ROOT, p), 'utf-8')
// 错误样本：去掉开头的 // expect 标注和“错误：……”说明，只留代码
const caseCode = (name: string) => {
  const lines = read(`problems/${PID}/cases/${name}`).split('\n')
  return lines.slice(lines.findIndex((l) => !l.startsWith('//'))).join('\n')
}

// 做题页第一次打开会自动弹出分步引导；除了专门测引导的用例，都当作已经看过
test.beforeEach(async ({ context }, info) => {
  if (!info.title.includes('分步引导')) {
    await context.addInitScript(() => { try { window.localStorage.setItem('tour.workbench.v1', '1') } catch { /* 忽略 */ } })
  }
})

async function login(page: Page, user: string) {
  await page.goto('/login')
  await page.getByTestId('login-name').fill(user)
  await page.getByTestId('login-password').fill(PASSWORD)
  await page.getByTestId('login-submit').click()
}

// 像学生一样把代码粘贴进编辑器（逐字键入会触发自动缩进）
async function setEditor(page: Page, code: string) {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.evaluate((text) => navigator.clipboard.writeText(text), code)
  const editor = page.getByTestId('code-editor').locator('.monaco-editor').first()
  await editor.locator('.view-lines').click()
  await page.keyboard.press('Control+A')
  await page.keyboard.press('Control+V')
  await expect(editor.locator('.view-lines')).toContainText('endmodule')
}

async function predict(page: Page, values: Record<number, '0' | '1'>, hw: { ff: number; ffSignals: string[] }) {
  await page.getByTestId('dock-wave').click()
  for (const [step, v] of Object.entries(values)) {
    const cell = page.getByTestId(`predict-out-${step}`)
    await cell.scrollIntoViewIfNeeded()
    await cell.click()                       // 第一次点击：0
    if (v === '1') await cell.click()        // 第二次点击：1
  }
  await page.getByTestId('dock-hw').click()
  await page.getByLabel('会综合出几个触发器').fill(String(hw.ff))
  await page.getByTestId('hardware-predict').getByText('无', { exact: true }).click()
  const select = page.getByTestId('hardware-predict').locator('.ant-select-selector')
  await select.click()
  for (const s of hw.ffSignals) {
    await page.keyboard.type(s)
    await page.keyboard.press('Enter')
  }
  await page.keyboard.press('Escape')
}

function eventTypes(login: string): string[] {
  const out = execFileSync('python3', ['-c', `
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
uid = db.execute("select id from users where login_name=?", (sys.argv[2],)).fetchone()[0]
print("\\n".join(r[0] for r in db.execute("select type from events where user_id=? order by ts", (uid,))))
`, E2E_DB, login], { encoding: 'utf-8' })
  return out.trim().split('\n')
}

test('学生从登录走完一道创作题的全部步骤', async ({ page }) => {
  const user = 'S2026002'
  const buggy = caseCode('c1_no_overlap.v')          // 检测到 101 后回到 S0，不允许重叠
  const ref = read(`problems/${PID}/ref.v`)

  // S1 登录 → 知情同意
  await login(page, user)
  await page.waitForURL('**/student/consent')
  await page.getByTestId('consent-accept').click()
  await page.waitForURL('**/student')
  await expect(page.getByTestId('home')).toBeVisible()

  // S3 题目列表 → S4 做题工作台
  await page.getByRole('link', { name: '题目', exact: true }).click()
  await page.getByTestId(`problem-row-${PID}`).getByRole('link').click()
  await expect(page.getByTestId('workbench')).toBeVisible()
  await expect(page.locator('.steps li.cur')).toContainText('预测')

  // ① 预测：写代码（先交一份有 bug 的），填波形预测格和硬件问题，锁定
  await setEditor(page, buggy)
  await predict(page, { 3: '1', 4: '0', 5: '1', 15: '0' }, { ff: 2, ffSignals: ['state'] })
  await page.getByTestId('btn-lock').click()
  await expect(page.locator('.steps li.cur')).toContainText('运行')

  // ② 运行
  await page.getByTestId('btn-run').click()
  await expect(page.getByTestId('first-mismatch')).toBeVisible({ timeout: 60_000 })
  await expect(page.locator('.steps li.cur')).toContainText('探究')
  await expect(page.getByTestId('quadrant-badge')).toBeVisible()
  await expect(page.getByTestId('pred-accuracy')).toContainText('预测准确率')

  // 提示阶梯：1 级思路（问题里点出第 5 步）
  await page.getByTestId('hint-request').click()
  await expect(page.getByTestId('hint-1')).toContainText('第 5 步')

  // ③ 探究：先点错格子，再点对；先点错代码行，再点对；写一句话解释
  await page.getByTestId('cell-actual-out-3').click()
  await expect(page.getByTestId('task-locate-step')).toContainText('再看看')
  const mm = page.getByTestId('cell-actual-out-5')
  await mm.scrollIntoViewIfNeeded()
  await mm.click()
  await expect(page.getByTestId('task-locate-step')).toContainText('STEP 5 · out ✓')
  const line = buggy.split('\n').findIndex((l) => l.includes('assign out')) + 1
  const lineNo = (n: number) => page.getByTestId('code-editor').locator('.line-numbers').filter({ hasText: new RegExp(`^${n}$`) })
  // 只读编辑器停在最后一行；用键盘回到开头（鼠标点代码会被算作一次“点出代码行”）
  await page.getByTestId('code-editor').locator('textarea').focus()
  await page.keyboard.press('Control+Home')
  await lineNo(1).click()
  await expect(page.getByTestId('task-locate-line')).toContainText('再看看')
  await lineNo(line).click()
  await expect(page.getByTestId('task-locate-line')).toContainText(`第 ${line} 行 ✓`)
  await page.getByTestId('explain-input').fill('检测到 101 之后直接回到了 S0，第 5 步重叠的那个 101 就丢了')
  await page.screenshot({ path: `${SHOTS}/workbench.png` })     // 关键页面 1：做题工作台（探究）
  await page.getByTestId('btn-explain').click()

  // 设计还没通过：重新预测并仿真
  await expect(page.locator('.steps li.cur')).toContainText('预测')
  await setEditor(page, ref)
  await predict(page, { 3: '1', 4: '0', 5: '1', 15: '0' }, { ff: 2, ffSignals: ['state'] })
  await page.getByTestId('btn-lock').click()
  await page.getByTestId('btn-run').click()
  await expect(page.getByTestId('quadrant-badge')).toHaveAttribute('data-quadrant', 'mastered', { timeout: 60_000 })

  // ⑤ 创作：写 testbench 并打分
  await expect(page.locator('.steps li.cur')).toContainText('创作')
  await page.getByTestId('tab-tb').click()
  await setEditor(page, read(`problems/${PID}/tb.v`))
  await page.getByTestId('btn-tb').click()
  await expect(page.getByTestId('task-done')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByTestId('tb-score').first()).toContainText('抓住了 4/4 个 bug')
  await expect(page.locator('.steps li.done')).toHaveCount(4)

  // S5 我的学情：状态机知识点按规则算出掌握等级
  await page.getByTestId('btn-back').click()
  await page.getByRole('link', { name: '我的学情' }).click()
  await expect(page.getByTestId('report')).toBeVisible()
  // 状态机：最近 2 次尝试 c = 0、1 → R_code = 1/2 < 2/3，按规则是“学习中”
  await expect(page.getByTestId('mastery-map').getByLabel('有限状态机：学习中')).toBeVisible()
  await expect(page.getByTestId('badges')).toContainText('testbench 满分')
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${SHOTS}/report.png`, fullPage: true })   // 关键页面 2：我的学情

  await page.getByRole('link', { name: '学习首页' }).click()
  await expect(page.getByTestId('home')).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/home.png`, fullPage: true })     // 关键页面 3：学习首页

  // 每一步都有事件日志
  await page.waitForTimeout(6000)            // 等界面事件批量上报（每 5 秒一批）
  const types = eventTypes(user)
  for (const t of ['auth.login', 'consent.accept', 'page.view', 'problem.open', 'step.enter', 'predict.submit',
    'code.submit', 'judge.done', 'waveform.view', 'waveform.cell_click', 'hint.request', 'hint.shown',
    'investigate.locate_step', 'investigate.locate_line', 'explain.submit', 'tb.submit']) {
    expect(types, `缺少事件 ${t}`).toContain(t)
  }
  expect(types.filter((t) => t === 'code.submit')).toHaveLength(2)
})

test('关键页面的布局与原型一致', async ({ page }) => {
  await login(page, 'S2026003')
  await page.getByTestId('consent-decline').click()      // 不参与研究也能照常使用
  await page.waitForURL('**/student')

  // 学生端顶部导航 56px，四个入口
  const nav = await page.locator('.topnav').boundingBox()
  expect(nav!.height).toBe(56)
  await expect(page.locator('.topnav nav a')).toHaveText(['学习首页', '新手入门', '题目', '复习', '我的学情'])

  // 我的学情：一行 4 张概览卡；掌握图 : 趋势图 = 7 : 5；底部三栏
  await page.goto('/student/report')
  const kpis = page.locator('.kpi')
  await expect(kpis).toHaveCount(4)
  const boxes = await Promise.all([0, 1, 2, 3].map((i) => kpis.nth(i).boundingBox()))
  expect(new Set(boxes.map((b) => Math.round(b!.y))).size).toBe(1)
  const [map, trend] = await Promise.all([page.locator('.g-7-5 > .card').nth(0).boundingBox(), page.locator('.g-7-5 > .card').nth(1).boundingBox()])
  expect(map!.width / trend!.width).toBeGreaterThan(1.25)
  expect(map!.width / trend!.width).toBeLessThan(1.55)
  await expect(page.locator('.g-5-4-4 > .card')).toHaveCount(3)
  await expect(page.getByText('这里不显示排名，也不和同学比较。')).toBeVisible()

  // 做题工作台：顶栏 56px；三栏可以拖动调宽（左右栏默认约 1/4）；中栏上编辑器、下波形
  await page.goto(`/student/problems/${PID}`)
  await expect(page.getByTestId('workbench')).toBeVisible()
  const top = await page.locator('.ws-top').boundingBox()
  expect(top!.height).toBe(56)
  await expect(page.getByTestId('next-step')).toContainText('下一步')
  const left = await page.getByTestId('col-left').boundingBox()
  const center = await page.getByTestId('col-center').boundingBox()
  const right = await page.getByTestId('col-right').boundingBox()
  expect(left!.width).toBeGreaterThan(280)
  expect(left!.width).toBeLessThan(center!.width)
  expect(right!.width).toBeLessThan(center!.width)
  expect(left!.x).toBeLessThan(center!.x)
  expect(center!.x + center!.width).toBeLessThan(right!.x)
  // 拖动左栏右边的分隔条，左栏变宽；题目说明完整显示，左栏可以上下滚动
  const bar = page.locator('.ws-body > .ant-splitter > .ant-splitter-bar').first().locator('.ant-splitter-bar-dragger')
  const bb = (await bar.boundingBox())!
  await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2)
  await page.mouse.down()
  await page.mouse.move(bb.x + 140, bb.y + bb.height / 2, { steps: 5 })
  await page.mouse.up()
  const wider = await page.getByTestId('col-left').boundingBox()
  expect(wider!.width).toBeGreaterThan(left!.width + 80)
  await expect(page.getByTestId('spec-card')).toContainText('端口')
  const scroll = await page.getByTestId('col-left').evaluate((el) => getComputedStyle(el).overflowY)
  expect(scroll).toBe('auto')
  const editor = await page.locator('.card.editor').boundingBox()
  const dock = await page.locator('.card.dock').boundingBox()
  expect(editor!.y).toBeLessThan(dock!.y)
  await expect(page.locator('.steps li')).toHaveCount(5)
  await expect(page.locator('.steps li.skip')).toContainText('修改')     // 创作题没有“修改”步骤
  // 右栏：本题状态 → 提示 → 问助教
  const titles = await page.getByTestId('col-right').locator('.card-h').allInnerTexts()
  expect(titles.map((t) => t.split(/\s/)[0])).toEqual(['本题状态', '提示', '问助教'])

  // 窗口太窄时提示在电脑上做题；“我的学情”“复习”在手机上单列显示、不出现横向滚动
  await page.setViewportSize({ width: 1000, height: 800 })
  await expect(page.getByTestId('narrow')).toContainText('请在电脑上做题')
  await page.setViewportSize({ width: 390, height: 844 })
  for (const path of ['/student/report', '/student/review']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow, path).toBeLessThanOrEqual(1)
  }
})

test('修改题：顺序打乱实验揭示竞争，再进入修改步骤', async ({ page }) => {
  await login(page, 'S2026004')
  await page.getByTestId('consent-accept').click()
  await page.waitForURL('**/student')
  await page.goto('/student/problems/swap_regs')
  await expect(page.locator('.steps li.cur')).toContainText('预测')
  // 起始代码只读；预测 x、y 第 2、3 步（总线：点击后输入十六进制）
  for (const [sig, step, v] of [['x', 2, '0x5'], ['x', 3, '0x3'], ['y', 2, '0x3'], ['y', 3, '0x5']] as const) {
    await page.getByTestId(`predict-${sig}-${step}`).click()
    await page.getByLabel(`${sig} 第 ${step} 步的预测值`).fill(v)
    await page.keyboard.press('Enter')
  }
  await page.getByTestId('dock-hw').click()
  await page.getByLabel('会综合出几个触发器').fill('8')
  await page.getByTestId('hardware-predict').getByText('无', { exact: true }).click()
  await page.getByTestId('btn-lock').click()
  await page.getByTestId('btn-run').click()
  await expect(page.locator('.steps li.cur')).toContainText('探究', { timeout: 60_000 })

  // 顺序打乱实验：预测“不会变”，结果却变了
  await page.getByTestId('dock-shuffle').click()
  await page.getByTestId('shuffle-predict-same').click()
  await page.getByTestId('shuffle-run').click()
  await expect(page.getByTestId('shuffle-diff')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByTestId('shuffle-diff')).toContainText('真实电路里这两个块谁先谁后？')
  await page.screenshot({ path: `${SHOTS}/shuffle.png` })
  await expect(page.getByTestId('col-right')).toContainText('结果依赖 always 块的先后顺序')
  await expect(page.getByTestId('col-right')).toContainText('以为结果取决于代码先后')

  // 完成探究 → 进入 ④ 修改，代码变为可编辑
  await page.getByTestId('dock-wave').click()
  await page.getByTestId('cell-actual-x-2').click()
  await expect(page.getByTestId('task-locate-step')).toContainText('✓')
  await page.getByTestId('code-editor').locator('textarea').focus()
  await page.keyboard.press('Control+Home')
  const line = read('problems/swap_regs/starter.v').split('\n').findIndex((l) => l.includes('else           x = y;')) + 1
  await page.getByTestId('code-editor').locator('.line-numbers').filter({ hasText: new RegExp(`^${line}$`) }).click()
  await expect(page.getByTestId('task-locate-line')).toContainText('✓')
  await page.getByTestId('explain-input').fill('两个块都用阻塞赋值，先执行的块改了 x，后面的块读到的已经是新值')
  await page.getByTestId('btn-explain').click()
  await expect(page.locator('.steps li.cur')).toContainText('修改')
  await expect(page.getByTestId('task-card')).toContainText('修改目标')
})

test('大模型不可用时：提示和对话都换成简化提示，照常做题', async ({ page }) => {
  // 端到端测试的后端没有配置 DEEPSEEK_API_KEY，相当于断网 / Key 无效
  await login(page, 'S2026001')
  await page.getByTestId('consent-accept').click()
  await page.waitForURL('**/student')
  await page.goto(`/student/problems/${PID}`)
  await setEditor(page, caseCode('c1_no_overlap.v'))
  await predict(page, { 3: '1', 4: '0', 5: '1', 15: '0' }, { ff: 2, ffSignals: ['state'] })
  await page.getByTestId('btn-lock').click()
  await page.getByTestId('btn-run').click()
  await expect(page.getByTestId('first-mismatch')).toBeVisible({ timeout: 60_000 })   // 仿真照常
  await page.getByTestId('hint-request').click()
  await expect(page.getByTestId('hint-1')).toContainText('第 5 步')
  await expect(page.getByTestId('hint-source')).toHaveText('当前为简化提示，不影响仿真和判定')
  await page.getByTestId('chat-input').fill('第 5 步为什么对不上？')
  await page.getByTestId('chat-send').click()
  await expect(page.getByTestId('chat-reply').last()).toContainText('当前为简化提示')
  await expect(page.getByTestId('chat-panel').locator('.card-h small')).toContainText('当前为简化提示，不影响仿真和判定')
})

test('新手入门：入门课、小测、分步引导、下一步高亮、术语解释', async ({ page }) => {
  await login(page, 'S2026005')
  await page.getByTestId('consent-accept').click()
  await page.waitForURL('**/student')
  await page.getByTestId('start-learn').click()
  await expect(page.getByTestId('learn')).toContainText('FPGA 和 Verilog 是什么')
  await page.getByTestId('lesson-what-is-fpga').click()
  const quiz = page.getByTestId('quiz').first()
  await quiz.getByTestId('quiz-option').nth(1).click()          // 第 1 题选对
  await expect(quiz).toContainText('答对了')
  await page.getByTestId('lesson-next').click()
  // 第 2 课的电路示意：点一下输入格子，输出跟着变
  const demo = page.getByTestId('demo')
  const before = await demo.locator('svg').innerHTML()
  await demo.getByTestId('demo-cell').first().click()
  expect(await demo.locator('svg').innerHTML()).not.toBe(before)
  // 首页没有布置作业时显示“接下来做”，入门题在前
  await page.goto('/student')
  await expect(page.getByTestId('next-problems')).toContainText('与门')
  // 入门题排在题目列表最前面，带“入门”标记；左侧没有“作业”筛选
  await page.goto('/student/problems')
  await expect(page.locator('tbody tr').first()).toContainText('入门')
  await expect(page.locator('tbody tr').first()).toContainText('与门')
  await expect(page.locator('.filters')).not.toContainText('作业')
  // 切换筛选：列表不闪成骨架屏（先保留旧列表，新结果到了再替换）
  for (const name of ['组合逻辑与 assign', '时序逻辑与触发器（时钟沿）', '全部']) {
    await page.locator('.filters').getByText(name, { exact: true }).first().click()
    await expect(page.locator('.problems .ant-skeleton')).toHaveCount(0)
    await expect(page.locator('.problems tbody tr').first()).toBeVisible()
  }

  // 第一次进入做题页：自动弹出分步引导，走完 8 步
  await page.goto('/student/problems/b1_and_gate')
  const tour = page.locator('.ant-tour')
  await expect(tour).toContainText('欢迎来到做题页')
  for (let i = 0; i < 7; i++) await tour.getByRole('button', { name: /下一步/ }).click()
  await tour.getByRole('button', { name: /结束引导|完成|结束/ }).click()
  await expect(tour).toBeHidden()
  // 下一步提示：先填波形 → 波形区闪烁；术语鼠标移上去有解释
  await expect(page.getByTestId('next-step')).toContainText('波形预测')
  await expect(page.locator('.card.dock.pulse-box')).toBeVisible()
  await page.getByTestId('term').filter({ hasText: '触发器' }).first().hover()
  await expect(page.locator('.ant-popover')).toContainText('能记住 1 位')
  // 预测题没有参考答案这一级
  await expect(page.getByTestId('answer-card')).toHaveCount(0)
  // 界面事件是分批上报的：等它们写进事件日志
  await expect.poll(() => eventTypes('S2026005'), { timeout: 30_000 })
    .toEqual(expect.arrayContaining(['lesson.open', 'lesson.quiz', 'tour.done']))
})

test('参考答案：提交 3 次没通过并看过代码提示后解锁', async ({ page }) => {
  await login(page, 'S2026006')
  await page.getByTestId('consent-accept').click()
  await page.waitForURL('**/student')
  await page.goto(`/student/problems/${PID}`)
  await expect(page.getByTestId('answer-card')).toContainText('再提交 3 次')
  // 用接口快速提交 3 次错误代码，并要到 3 级代码提示
  const aid = await page.evaluate(async ([pid, code]) => {
    const call = async (m: string, u: string, b?: unknown) => (await fetch(u, { method: m, credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined })).json()
    const d = await call('GET', `/api/student/problems/${pid}`)
    let last = 0
    for (let i = 0; i < 3; i++) {
      const cells = d.predict_points.flatMap((p: any) => p.steps.map((s: number) => ({ signal: p.signal, step: s, value: '0' })))
      await call('POST', `/api/student/problems/${pid}/predictions`, { waveform: { cells }, hardware: { ff_count: 2, latch: false, ff_signals: [] } })
      last = (await call('POST', `/api/student/problems/${pid}/attempts`, { code })).attempt_id
      for (let k = 0; k < 120; k++) {
        if ((await call('GET', `/api/student/attempts/${last}`)).status === 'done') break
        await new Promise((r) => setTimeout(r, 500))
      }
    }
    for (let lv = 0; lv < 3; lv++) {
      await call('POST', `/api/student/attempts/${last}/hints`)
      await call('POST', `/api/student/attempts/${last}/investigations`, { kind: 'locate_step', chosen: { step: 0, signal: 'out' } })
    }
    return last
  }, [PID, caseCode('c1_no_overlap.v')] as const)
  expect(aid).toBeGreaterThan(0)
  await page.reload()
  await expect(page.getByTestId('hint-3').getByTestId('code-block')).toContainText('____')
  await page.getByTestId('answer-open').click()
  await page.getByRole('button', { name: '看参考答案', exact: true }).click()
  await expect(page.locator('.ant-modal').filter({ hasText: '参考答案' }).getByTestId('code-block')).toContainText('S101')
  await expect(page.locator('.ant-modal-confirm')).toHaveCount(0)
  await page.waitForTimeout(400)                       // 等弹窗动画结束再截图
  await page.screenshot({ path: `${SHOTS}/answer.png` })
  expect(eventTypes('S2026006')).toContain('answer.reveal')
})
