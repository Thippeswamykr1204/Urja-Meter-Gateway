import { test, expect } from '@playwright/test'

test('console opens the overview surface', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /see the grid/i })).toBeVisible()
  await expect(page.getByText('Indexed meters')).toBeVisible()
  await page.getByRole('link', { name: /meter explorer/i }).click()
  await expect(page.getByRole('heading', { name: /meter explorer/i })).toBeVisible()
  await page.keyboard.press('Meta+K')
  await expect(page.getByRole('dialog', { name: /command palette/i })).toBeVisible()
})
