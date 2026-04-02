const { test, expect } = require('@playwright/test');

test.describe('index_mm.html (Market Maker UI)', () => {
  test('loads and displays price data', async ({ page }) => {
    await page.goto('/index_mm.html');
    await expect(page).toHaveTitle(/OrdexSwap/i);
    
    // Check main elements are present
    await expect(page.locator('#from-amount')).toBeVisible();
    await expect(page.locator('#to-amount')).toBeVisible();
    await expect(page.locator('#swap-btn')).toBeVisible();
    await expect(page.locator('#price-chart')).toBeVisible();
  });

  test('enables swap with valid input', async ({ page }) => {
    await page.goto('/index_mm.html');

    const amount = page.locator('#from-amount');
    const address = page.locator('#user-address');
    const button = page.locator('#swap-btn');

    // Fill amount (10 OXC, production requires min 1.0)
    await amount.fill('10');
    
    // Wait for quote response with longer timeout for production
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // If API doesn't respond, we can still test basic form functionality
      console.log('Quote API not responding, testing form validation');
    }

    // Fill valid address
    await address.fill('user_addr_12345');
    await page.waitForTimeout(500);

    // Button should be enabled
    await expect(button).toBeEnabled();
  });

  test('blocks invalid input and shows error', async ({ page }) => {
    await page.goto('/index_mm.html');

    const amount = page.locator('#from-amount');
    const address = page.locator('#user-address');
    const button = page.locator('#swap-btn');

    // Test negative amount - button should be disabled
    await amount.fill('-5');
    await page.waitForTimeout(200);
    await expect(button).toBeDisabled();

    // Test valid amount
    await amount.fill('10');
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // API may be slow, still test address validation
    }

    // Test invalid address
    await address.fill('bad!');
    await page.waitForTimeout(200);
    await expect(button).toBeDisabled();
    await expect(page.locator('#address-error')).toBeVisible();
  });

  test('swap direction toggle works', async ({ page }) => {
    await page.goto('/index_mm.html');

    const fromCoin = page.locator('#from-coin');
    const toCoin = page.locator('#to-coin');
    const swapDirection = page.locator('#swap-direction');

    // Initial values
    await expect(fromCoin).toHaveValue('OXC');
    await expect(toCoin).toHaveValue('OXG');

    // Click swap direction button
    await swapDirection.click();
    await page.waitForTimeout(100);

    // Values should be swapped
    await expect(fromCoin).toHaveValue('OXG');
    await expect(toCoin).toHaveValue('OXC');
  });

  test('handles amount limits correctly', async ({ page }) => {
    await page.goto('/index_mm.html');

    const amount = page.locator('#from-amount');
    const button = page.locator('#swap-btn');
    const address = page.locator('#user-address');

    // Test amounts that should disable button
    await amount.fill('0');
    await page.waitForTimeout(100);
    await expect(button).toBeDisabled();

    await amount.fill('-1');
    await page.waitForTimeout(100);
    await expect(button).toBeDisabled();

    // Test valid amount
    await amount.fill('10');
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // Continue even if API doesn't respond
    }

    // With valid address, button should be enabled
    await address.fill('valid_address_123');
    await page.waitForTimeout(500);
    await expect(button).toBeEnabled();
  });

  test('reset button clears form', async ({ page }) => {
    await page.goto('/index_mm.html');

    const amount = page.locator('#from-amount');
    const address = page.locator('#user-address');
    const button = page.locator('#swap-btn');
    const resetBtn = page.locator('#reset-btn');

    // Fill form
    await amount.fill('10');
    await address.fill('test_address');
    
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // Continue even if API doesn't respond
    }
    await page.waitForTimeout(300);

    // Click reset
    await resetBtn.click();
    await page.waitForTimeout(100);

    // Form should be cleared
    await expect(amount).toHaveValue('');
    await expect(address).toHaveValue('');
    await expect(button).toBeDisabled();
  });

  test('displays price chart after loading', async ({ page }) => {
    await page.goto('/index_mm.html');

    const priceChart = page.locator('#price-chart');

    // Wait for price chart to load or show error/empty state
    await page.waitForFunction(() => {
      const chart = document.getElementById('price-chart');
      if (!chart) return false;
      const svg = chart.querySelector('svg');
      if (svg) return true;
      const text = chart.textContent || '';
      return text.includes('No data') || text.includes('Flux') || text.includes('Initializing');
    }, null, { timeout: 20000 });

    // Chart container should be present
    await expect(priceChart).toBeVisible();
  });

  test('validates address format', async ({ page }) => {
    await page.goto('/index_mm.html');

    const address = page.locator('#user-address');
    const addressError = page.locator('#address-error');
    const button = page.locator('#swap-btn');

    // Fill amount first 
    await page.locator('#from-amount').fill('10');
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // Continue even if API doesn't respond
    }

    // Test invalid addresses
    await address.fill('short');
    await page.waitForTimeout(200);
    await expect(addressError).toBeVisible();
    await expect(button).toBeDisabled();

    await address.fill('bad!');
    await page.waitForTimeout(200);
    await expect(addressError).toBeVisible();

    // Test valid address
    await address.fill('valid_address_123');
    await page.waitForTimeout(200);
    await expect(addressError).toHaveClass(/d-none/);
    await expect(button).toBeEnabled();
  });
});
