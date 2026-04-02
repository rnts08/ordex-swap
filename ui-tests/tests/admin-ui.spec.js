const { test, expect } = require('@playwright/test');

test('admin dashboard login hides login card and shows graphs', async ({ page }) => {
  await page.goto('/admin.html');

  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  const loginBtn = page.locator('#login-btn');
  await loginBtn.click();

  const dashboard = page.locator('#dashboard');
  const loginCard = page.locator('#login-card');

  await expect(dashboard).toBeVisible();
  await expect(loginCard).toHaveClass(/d-none/);

  await expect(page.locator('#inout-graph')).toBeVisible();
  await expect(page.locator('#status-graph')).toBeVisible();

  await expect(page.locator('#pw-user')).toBeVisible();
  await expect(page.locator('#pw-current')).toBeVisible();
  await expect(page.locator('#pw-new')).toBeVisible();
});

test('rotate buttons show confirmation dialog', async ({ page }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toMatch(/Rotate liquidity address/i);
    await dialog.dismiss();
  });

  const rotateLiquidity = page.locator('text=Rotate Liquidity').first();
  await rotateLiquidity.click();
});

test('swap control shows enable/disable buttons', async ({ page }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  await expect(page.locator('#swapcontrol')).toBeVisible();
  await expect(page.locator('#enable-swaps')).toBeVisible();
  await expect(page.locator('#disable-swaps')).toBeVisible();
  await expect(page.locator('#swap-status-badge')).toBeVisible();
});

test('swap control requires admin login', async ({ page }) => {
  await page.goto('/admin.html');
  
  await expect(page.locator('#swapcontrol')).not.toBeVisible();
  await expect(page.locator('#enable-swaps')).not.toBeVisible();
  await expect(page.locator('#disable-swaps')).not.toBeVisible();
});

test('can disable and enable swaps via admin', async ({ page, request }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  const enableBtn = page.locator('#enable-swaps');
  const disableBtn = page.locator('#disable-swaps');
  const badge = page.locator('#swap-status-badge');
  const msg = page.locator('#swap-control-message');

  await expect(badge).toHaveText(/Enabled/);

  page.on('dialog', async (dialog) => {
    await dialog.accept();
  });

  await disableBtn.click();
  await expect(msg).toHaveText(/Swaps disabled/, { timeout: 10000 });
  await expect(badge).toHaveText(/Disabled/);

  let status = await request.get('http://localhost:8080/api/v1/status');
  let statusData = await status.json();
  expect(statusData.data.swaps_enabled).toBe(false);

  await enableBtn.click();
  await expect(msg).toHaveText(/Swaps enabled/, { timeout: 10000 });
  await expect(badge).toHaveText(/Enabled/);

  status = await request.get('http://localhost:8080/api/v1/status');
  statusData = await status.json();
  expect(statusData.data.swaps_enabled).toBe(true);
});

test('withdraw section shows input fields', async ({ page }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  await expect(page.locator('#withdraw')).toBeVisible();
  await expect(page.locator('#withdraw-coin')).toBeVisible();
  await expect(page.locator('#withdraw-purpose')).toBeVisible();
  await expect(page.locator('#withdraw-amount')).toBeVisible();
  await expect(page.locator('#withdraw-address')).toBeVisible();
  await expect(page.locator('#withdraw-btn')).toBeVisible();
  await expect(page.locator('#wallet-actions-table')).toBeVisible();
});

test('withdraw validates input and shows error for invalid address', async ({ page }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  await page.locator('#withdraw-coin').selectOption('OXC');
  await page.locator('#withdraw-amount').fill('0.01');
  await page.locator('#withdraw-address').fill('invalidaddr');
  await page.locator('#withdraw-btn').click();

  const msg = page.locator('#withdraw-message');
  await expect(msg).toBeVisible();
});

test('wallet actions are recorded in history', async ({ page, request }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  const auth = 'Basic ' + btoa('swap:changeme26');
  const baseUrl = process.env.UI_BASE_URL || 'http://localhost:8080';
  const resp = await request.get(baseUrl + '/api/v1/admin/wallets/actions', {
    headers: { Authorization: auth }
  });
  const data = await resp.json();
  expect(data.success).toBe(true);
  expect(data.data.actions.length).toBeGreaterThan(0);
  await expect(page.locator('#wallet-actions-table')).toContainText('withdraw_failed');
});

test('settings configuration section is visible and functional', async ({ page, request }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  const feeConfig = page.locator('#feeconfig');
  await expect(feeConfig).toBeVisible();

  await expect(page.locator('#fee-percent')).toBeVisible();
  await expect(page.locator('#confirmations-required')).toBeVisible();
  await expect(page.locator('#min-fee-oxc')).toBeVisible();
  await expect(page.locator('#min-fee-oxg')).toBeVisible();
  await expect(page.locator('#min-amount')).toBeVisible();
  await expect(page.locator('#max-amount')).toBeVisible();
  await expect(page.locator('#timeout-mins')).toBeVisible();
  await expect(page.locator('#update-settings')).toBeVisible();
});

test('can update settings via admin interface', async ({ page, request }) => {
  await page.goto('/admin.html');
  await page.locator('#admin-user').fill('swap');
  await page.locator('#admin-pass').fill('changeme26');
  await page.locator('#login-btn').click();
  await expect(page.locator('#dashboard')).toBeVisible();

  await page.locator('#fee-percent').fill('2.5');
  await page.locator('#timeout-mins').fill('25');
  await page.locator('#update-settings').click();

  const msg = page.locator('#settings-message');
  await expect(msg).toContainText(/updated successfully/i, { timeout: 10000 });

  const auth = 'Basic ' + btoa('swap:changeme26');
  const resp = await request.get('http://localhost:8080/api/v1/admin/settings', {
    headers: { Authorization: auth }
  });
  const data = await resp.json();
  expect(data.success).toBe(true);
  expect(data.data.swap_fee_percent).toBe(2.5);
  expect(data.data.swap_expire_minutes).toBe(25);
});
