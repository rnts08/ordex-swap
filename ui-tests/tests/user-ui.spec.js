const { test, expect } = require('@playwright/test');

test('user UI loads and enables swap with valid input', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/OrdexSwap/i);

  const amount = page.locator('#from-amount');
  const address = page.locator('#user-address');
  const button = page.locator('#swap-btn');
  const priceChart = page.locator('#price-chart');

  await amount.fill('10');
  await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200);

  await address.fill('user_addr_12345');
  await page.waitForTimeout(300);

  await expect(button).toBeEnabled();
  await expect(page.locator('#btn-text')).toContainText(/Create Swap/i);

  await page.waitForFunction(() => {
    const chart = document.getElementById('price-chart');
    if (!chart) return false;
    const bars = chart.querySelectorAll('.price-bar');
    const text = chart.textContent || '';
    if (text.includes('Loading chart') || text.includes('No history data') || text.includes('No price data')) {
      return false;
    }
    return bars.length > 0;
  }, null, { timeout: 15000 });

  const barCount = await priceChart.locator('.price-bar').count();
  expect(barCount).toBeGreaterThan(0);
});

test('user UI blocks invalid input and shows error on submit', async ({ page }) => {
  await page.goto('/');

  const amount = page.locator('#from-amount');
  const address = page.locator('#user-address');
  const button = page.locator('#swap-btn');
  const messageArea = page.locator('#message-area');

  await amount.fill('-5');
  await page.waitForTimeout(200);
  await expect(button).toBeDisabled();

  await amount.fill('10');
  await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200);

  await address.fill('bad!');
  await page.waitForTimeout(200);
  await expect(button).toBeDisabled();

  await page.locator('#swap-form').evaluate((form) => form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })));
  await expect(messageArea).toContainText(/valid receiving address/i);
});

test('user UI fuzzes input fields without enabling swap for invalid values', async ({ page }) => {
  await page.goto('/');

  const amount = page.locator('#from-amount');
  const address = page.locator('#user-address');
  const button = page.locator('#swap-btn');

  const badAmounts = ['0', '-1', '0.00001', ''];
  for (const value of badAmounts) {
    await amount.fill(value);
    await page.waitForTimeout(100);
    await expect(button).toBeDisabled();
  }

  await amount.fill('10');
  await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200);

  const badAddresses = ['short', 'bad!', ' space', 'x'.repeat(200)];
  for (const value of badAddresses) {
    await address.fill(value);
    await page.waitForTimeout(100);
    await expect(button).toBeDisabled();
  }
});
