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
