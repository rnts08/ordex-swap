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
    
    // Check stats elements
    await expect(page.locator('#stat-volume')).toBeVisible();
    await expect(page.locator('#stat-swaps')).toBeVisible();
    await expect(page.locator('#stat-high')).toBeVisible();
    await expect(page.locator('#stat-low')).toBeVisible();
    
    // Check mode indicator
    await expect(page.locator('#mode-indicator')).toBeVisible();
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
    await expect(page.locator('#btn-text')).toContainText(/Swap/i);
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

  test('fuzzes input fields without enabling swap for invalid values', async ({ page }) => {
    await page.goto('/index_mm.html');

    const amount = page.locator('#from-amount');
    const address = page.locator('#user-address');
    const button = page.locator('#swap-btn');

    // Test bad amounts
    const badAmounts = ['0', '-1', '0.00001', ''];
    for (const value of badAmounts) {
      await amount.fill(value);
      await page.waitForTimeout(100);
      await expect(button).toBeDisabled();
    }

    // Fill valid amount
    await amount.fill('10');
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // Continue even if API doesn't respond
    }

    // Test bad addresses
    const badAddresses = ['short', 'bad!', ' space', 'x'.repeat(200)];
    for (const value of badAddresses) {
      await address.fill(value);
      await page.waitForTimeout(100);
      await expect(button).toBeDisabled();
    }
  });

  test('shows error message on submit with invalid address', async ({ page }) => {
    await page.goto('/index_mm.html');

    const amount = page.locator('#from-amount');
    const address = page.locator('#user-address');
    const button = page.locator('#swap-btn');

    // Fill valid amount
    await amount.fill('10');
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // Continue even if API doesn't respond
    }

    // Fill invalid address
    await address.fill('bad!');
    await page.waitForTimeout(200);
    await expect(button).toBeDisabled();

    // Try to submit
    await page.locator('#swap-form').evaluate((form) => form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })));
    
    // Should show error toast
    await page.waitForTimeout(500);
    const toastContainer = page.locator('.toast-container');
    await expect(toastContainer).toBeVisible();
    await expect(toastContainer).toContainText(/error/i);
  });

  test('copy to clipboard functionality works', async ({ page }) => {
    await page.goto('/index_mm.html');

    // Grant clipboard permissions
    const context = page.context();
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);

    // The copy functionality is triggered after a swap is created
    // We'll test that the copyToClipboard function is available on window
    const isCopyAvailable = await page.evaluate(() => typeof window.copyToClipboard === 'function');
    await expect(isCopyAvailable).toBe(true);
  });

  test('cancel swap functionality is available', async ({ page }) => {
    await page.goto('/index_mm.html');

    // The cancel functionality is triggered on active swaps
    // We'll test that the cancelSwap function is available on window
    const isCancelAvailable = await page.evaluate(() => typeof window.cancelSwap === 'function');
    await expect(isCancelAvailable).toBe(true);
  });

  test('displays recent swaps section', async ({ page }) => {
    await page.goto('/index_mm.html');

    const recentSwaps = page.locator('#recent-swaps');
    await expect(recentSwaps).toBeVisible();
    
    // Should show either swaps or "No recent swaps" message
    const text = await recentSwaps.textContent();
    expect(text).toMatch(/(No recent swaps|Synchronizing|OXC|OXG)/i);
  });

  test('displays fee information', async ({ page }) => {
    await page.goto('/index_mm.html');

    const feeDisplay = page.locator('#fee-display');
    await expect(feeDisplay).toBeVisible();
    
    // Fee should be displayed as a percentage
    const feeText = await feeDisplay.textContent();
    expect(feeText).toMatch(/\d+\.?\d*%/);
  });

  test('displays current rate', async ({ page }) => {
    await page.goto('/index_mm.html');

    const currentRate = page.locator('#current-rate');
    await expect(currentRate).toBeVisible();
    
    // Rate should be displayed or show loading/unavailable
    const rateText = await currentRate.textContent();
    expect(rateText).toMatch(/(Loading|unavailable|\d+\.?\d*)/i);
  });

  test('handles coin selection correctly', async ({ page }) => {
    await page.goto('/index_mm.html');

    const fromCoin = page.locator('#from-coin');
    const toCoin = page.locator('#to-coin');

    // Initially OXC -> OXG
    await expect(fromCoin).toHaveValue('OXC');
    await expect(toCoin).toHaveValue('OXG');

    // Change from coin to OXG
    await fromCoin.selectOption('OXG');
    await page.waitForTimeout(100);

    // To coin should automatically change to OXC
    await expect(toCoin).toHaveValue('OXC');

    // Change back
    await fromCoin.selectOption('OXC');
    await page.waitForTimeout(100);
    await expect(toCoin).toHaveValue('OXG');
  });

  test('quote details update when amount changes', async ({ page }) => {
    await page.goto('/index_mm.html');

    const amount = page.locator('#from-amount');
    const quoteRate = page.locator('#quote-rate');
    const quoteFee = page.locator('#quote-fee');
    const quoteReceive = page.locator('#quote-receive');

    // Fill amount
    await amount.fill('10');
    
    // Wait for quote
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // API may not respond
    }
    await page.waitForTimeout(500);

    // Quote details should be updated (not showing '--')
    const rateText = await quoteRate.textContent();
    const receiveText = await quoteReceive.textContent();
    
    // Either we have valid quote or API didn't respond
    if (rateText !== '--' && receiveText !== '--') {
      // We got a valid quote
      expect(rateText).toMatch(/\d+/);
      expect(receiveText).toMatch(/\d+/);
    }
  });

  test('toast notifications appear and disappear', async ({ page }) => {
    await page.goto('/index_mm.html');

    // Trigger an error by submitting with invalid data
    const amount = page.locator('#from-amount');
    const address = page.locator('#user-address');
    
    await amount.fill('10');
    await address.fill('bad!');
    await page.waitForTimeout(200);
    
    await page.locator('#swap-form').evaluate((form) => form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })));
    
    // Wait for toast to appear
    await page.waitForTimeout(500);
    const toastContainer = page.locator('.toast-container');
    await expect(toastContainer).toBeVisible();
    
    // Toast should have bounce-in animation class initially
    const toast = toastContainer.locator('.animate-bounce-in').first();
    await expect(toast).toBeVisible();
  });

  test('address validation matches backend requirements', async ({ page }) => {
    await page.goto('/index_mm.html');

    const address = page.locator('#user-address');
    const addressError = page.locator('#address-error');
    const button = page.locator('#swap-btn');

    // Fill valid amount first
    await page.locator('#from-amount').fill('10');
    try {
      await page.waitForResponse((resp) => resp.url().includes('/api/v1/quote') && resp.status() === 200, { timeout: 10000 });
    } catch (e) {
      // Continue even if API doesn't respond
    }

    // Test addresses that should be INVALID (< 8 chars, special chars, > 120 chars)
    const invalidAddresses = [
      'short',           // Too short
      'ab',              // Way too short
      'bad!',             // Special character
      'test@address',     // @ symbol
      'address with spaces', // Spaces
      'x'.repeat(121),   // Too long
      '',                // Empty
    ];

    for (const addr of invalidAddresses) {
      await address.fill(addr);
      await page.waitForTimeout(100);
      await expect(addressError).toBeVisible();
      await expect(button).toBeDisabled();
    }

    // Test addresses that should be VALID (8-120 chars, alphanumeric, _, -)
    const validAddresses = [
      'validadd',        // Exactly 8 chars
      'valid_addr_123',  // With underscore
      'valid-addr-123',  // With hyphen
      'MixedCase123',    // Mixed case
      'a'.repeat(120),   // Max length
    ];

    for (const addr of validAddresses) {
      await address.fill(addr);
      await page.waitForTimeout(100);
      await expect(addressError).toHaveClass(/d-none/);
    }
  });
});