const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: process.env.UI_BASE_URL || 'http://localhost:8080',
    headless: true,
  },
  retries: 1,
});
