const { test, expect } = require('@playwright/test');

test('user UI loads and enables swap with valid input', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/OrdexSwap/i);

  const amount = page.locator('#from-amount');
  const address = page.locator('#user-address');
  const button = page.locator('#swap-btn');

  await amount.fill('10');
  await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200);

  await address.fill('user_addr_12345');
  await page.waitForTimeout(300);

  await expect(button).toBeEnabled();
  await expect(page.locator('#btn-text')).toContainText(/Create Swap/i);
});
