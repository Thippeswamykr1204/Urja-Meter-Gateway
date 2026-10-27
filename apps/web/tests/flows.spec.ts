import { expect, test } from '@playwright/test'

test('overview renders KPIs from demo data', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Indexed meters')).toBeVisible()
  await expect(page.getByText('Reporting normally')).toBeVisible()
})

test('explorer search and sort survive a reload', async ({ page }) => {
  await page.goto('/meters')
  await page.getByRole('textbox', { name: 'Search meters' }).fill('North')
  await expect(page).toHaveURL(/search=North/)
  await page.getByRole('button', { name: /Meter/ }).click()
  await expect(page).toHaveURL(/sort=name/)
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Search meters' })).toHaveValue('North')
  await expect(page).toHaveURL(/sort=name/)
})

test('meter detail controls change the consumption request', async ({ page }) => {
  const requests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/consumption')) requests.push(request.url())
  })
  await page.goto('/meters/MTR-1001')
  await expect(page.getByRole('heading', { name: /North feeder/i })).toBeVisible()
  await page.getByRole('combobox', { name: 'Consumption range' }).selectOption('30')
  await page.getByRole('combobox', { name: 'Consumption granularity' }).selectOption('month')
  await expect.poll(() => requests.some((url) => url.includes('granularity=month'))).toBe(true)
})

test('hierarchy expands and collapses by keyboard', async ({ page }) => {
  await page.goto('/hierarchy')
  const root = page.getByRole('button', { name: /Distribution grid/ }).first()
  await expect(root).toHaveAttribute('aria-expanded', 'true')
  await root.press('ArrowLeft')
  await expect(root).toHaveAttribute('aria-expanded', 'false')
  await root.press('ArrowRight')
  await expect(root).toHaveAttribute('aria-expanded', 'true')
})

test('API-down error recovers after retry', async ({ page }) => {
  let failures = 2
  await page.route('**/api/v1/overview*', async (route) => {
    if (failures > 0) {
      failures -= 1
      await route.abort()
      return
    }
    await route.continue()
  })
  await page.goto('/')
  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByRole('button', { name: /try again/i }).click()
  await expect(page.getByText('Indexed meters')).toBeVisible()
})

test('stale response shows the stale banner', async ({ page }) => {
  await page.route('**/api/v1/overview*', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.provenance.stale = true
    await route.fulfill({ response, json: body })
  })
  await page.goto('/')
  await expect(page.getByRole('status').filter({ hasText: 'Stale data' })).toBeVisible()
})

test('light theme keeps interactive surfaces bright without horizontal overflow', async ({ page }) => {
  await page.goto('/map')
  await page.getByRole('button', { name: /switch to light theme/i }).click()

  const luminance = (color: string) => {
    const channels = color.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [0, 0, 0]
    const normalized = channels.map((channel) => channel / 255).map((channel) => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
    return normalized[0] * 0.2126 + normalized[1] * 0.7152 + normalized[2] * 0.0722
  }
  const backgroundLuminance = async (locator: ReturnType<typeof page.locator>) => locator.evaluate((element) => getComputedStyle(element).backgroundColor).then(luminance)

  await page.locator('.nav-link').nth(1).hover()
  await expect.poll(() => backgroundLuminance(page.locator('.nav-link').nth(1))).toBeGreaterThan(0.7)
  await expect.poll(() => backgroundLuminance(page.getByRole('textbox', { name: 'Center latitude' }))).toBeGreaterThan(0.7)

  await page.goto('/meters')
  await expect.poll(() => backgroundLuminance(page.getByRole('textbox', { name: 'Search meters' }))).toBeGreaterThan(0.7)
  await page.goto('/meters/MTR-1001')
  await page.getByRole('button', { name: 'Data trust' }).click()
  await expect.poll(() => backgroundLuminance(page.getByRole('dialog', { name: 'Data trust' }))).toBeGreaterThan(0.7)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
})
