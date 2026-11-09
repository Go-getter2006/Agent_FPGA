// 阶段 5：教师端各页面（数据来自 2 组 × 30 名虚拟学生 × 20 次尝试的生成数据）
import { expect, test, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SHOTS = resolve(HERE, 'screenshots')
const PASSWORD = process.env.DEMO_PASSWORD ?? 'e2e-pass-123'
const E2E_DB = `${process.env.E2E_DIR ?? '/tmp/agent_fpga_e2e'}/e2e.db`

async function loginTeacher(page: Page) {
  await page.goto('/login')
  await page.getByTestId('login-name').fill('TGEN')
  await page.getByTestId('login-password').fill(PASSWORD)
  await page.getByTestId('login-submit').click()
  await page.waitForURL(/\/teacher\/classes\/\d+$/)
  return page.url().match(/classes\/(\d+)/)![1]
}

function sqlite(query: string): string {
  return execFileSync('python3', ['-c', 'import sqlite3,sys;print("\\n".join("|".join(map(str,r)) for r in sqlite3.connect(sys.argv[1]).execute(sys.argv[2])))',
    E2E_DB, query], { encoding: 'utf-8' }).trim()
}

test('班级概览的布局与原型一致', async ({ page }) => {
  const cid = await loginTeacher(page)
  await expect(page.getByTestId('t-overview')).toBeVisible()
  // 左侧菜单 220px；顶栏 56px；KPI 卡一行 5 张
  expect(Math.round((await page.locator('.side').boundingBox())!.width)).toBe(220)
  expect((await page.locator('.t-top').boundingBox())!.height).toBe(56)
  const kpis = page.locator('.g5 .kpi')
  await expect(kpis).toHaveCount(5)
  const ys = await Promise.all([0, 1, 2, 3, 4].map(async (i) => Math.round((await kpis.nth(i).boundingBox())!.y)))
  expect(new Set(ys).size).toBe(1)
  await expect(kpis.nth(0)).toContainText('本周活跃')
  await expect(page.locator('.side a')).toHaveText(['▦班级概览', '▤学情热力图', '◎误区分析', '▥题目分析', '☰学生详情',
    '✎作业与题库', '☷班级管理', '⚗实验分组与导出'])
  await expect(page.locator('.t-top')).toContainText('实验组 30 人 · 对照组 30 人')
  await expect(page.getByTestId('anonymous-switch')).toBeChecked()
  // 趋势 : 误区 = 5 : 7；热力图节选 : 预警 = 7 : 5
  const [trend, mis] = await Promise.all([page.locator('.g-5-7 > .card').nth(0).boundingBox(), page.locator('.g-5-7 > .card').nth(1).boundingBox()])
  expect(trend!.width / mis!.width).toBeGreaterThan(0.6)
  expect(trend!.width / mis!.width).toBeLessThan(0.8)
  await expect(page.getByTestId('t-mis-top').locator('.hbar')).toHaveCount(5)
  await expect(page.getByTestId('t-alerts').locator('.row').first()).toBeVisible()
  await expect(page.getByTestId('t-alerts').locator('.row b').first()).toHaveText(/^S\d\d$/)      // 默认匿名
  await expect(page.getByTestId('t-problems').locator('tbody tr')).toHaveCount(6)
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${SHOTS}/teacher-overview.png`, fullPage: true })

  // 关闭匿名：显示真实姓名，并写一条事件
  await page.getByTestId('anonymous-switch').click()
  await expect(page.getByTestId('t-alerts').locator('.row b').first()).toContainText('虚拟学生')
  expect(sqlite(`select count(*) from events where type='teacher.anonymity' and class_id=${cid}`)).toBe('1')
})

test('热力图、误区、题目分析、学生详情', async ({ page }) => {
  const cid = await loginTeacher(page)
  await page.getByRole('link', { name: /学情热力图/ }).click()
  await expect(page.getByTestId('heatmap-chart').locator('svg')).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/teacher-heatmap.png`, fullPage: true })

  await page.getByRole('link', { name: /误区分析/ }).click()
  await page.getByTestId('t-misconceptions').locator('.hbar').first().click()
  await expect(page.getByTestId('mis-detail')).toContainText('典型代码片段（匿名）')
  await expect(page.getByTestId('mis-detail').locator('.snippet').first()).toBeVisible()

  await page.getByRole('link', { name: /题目分析/ }).click()
  await expect(page.getByTestId('funnel')).toBeVisible()
  await expect(page.getByTestId('after-hint').locator('tbody tr').first()).toBeVisible()

  await page.getByRole('link', { name: /学生详情/ }).click()
  await expect(page.getByTestId('tl-row')).toHaveCount(20)
  await page.getByTestId('tl-row').first().click()
  await expect(page.getByTestId('attempt-detail')).toBeVisible()
  expect(cid).toBeTruthy()
})

test('分组与开关、导出、名单', async ({ page }) => {
  const cid = await loginTeacher(page)
  await page.getByRole('link', { name: /实验分组与导出/ }).click()
  await expect(page.getByTestId('flag-control-predict_step')).not.toBeChecked()   // 对照组默认关闭预测
  await page.getByTestId('flag-control-review').click()
  await page.getByTestId('save-groups').click()
  await expect(page.getByText('分组与功能开关已保存')).toBeVisible()
  expect(sqlite(`select json_extract(flags,'$.review') from feature_flags where class_id=${cid} and "group"='control'`)).toBe('0')
  await page.getByTestId('start-export').click()
  await expect(page.getByTestId('export-done')).toContainText('名学生的数据', { timeout: 60_000 })
  const download = page.waitForEvent('download')
  await page.getByTestId('export-done').getByRole('link', { name: '下载 zip' }).click()
  expect((await download).suggestedFilename()).toMatch(/\.zip$/)
  await page.screenshot({ path: `${SHOTS}/teacher-research.png`, fullPage: true })

  await page.getByRole('link', { name: /班级管理/ }).click()
  await expect(page.getByTestId('t-roster')).toContainText('虚拟学生01')                 // 名单页显示真实姓名
  await page.getByTestId('roster-csv').fill('学号,姓名\nE2E0001,端到端同学')
  await page.getByTestId('roster-import').click()
  await expect(page.getByTestId('roster-result')).toContainText('E2E0001')
})

test('学生不能进入教师端', async ({ page }) => {
  await page.goto('/login')
  await page.getByTestId('login-name').fill('S2026004')
  await page.getByTestId('login-password').fill(PASSWORD)
  await page.getByTestId('login-submit').click()
  await page.waitForURL(/student/)
  await page.goto('/teacher/classes/1')
  await expect(page).toHaveURL(/\/student/)
})
