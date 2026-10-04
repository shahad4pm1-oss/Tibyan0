import { defineConfig, devices } from "@playwright/test";

// Browser E2E against a running stack: backend on :8000 (no LLM configured, rate limit disabled for the run)
// and `vite preview` on :4173. See docs/OPERATIONS.md ("Running the browser E2E suite").
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "e2e-results.json" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173",
    locale: "ar",
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 820, height: 1180 }, hasTouch: true } },
    { name: "mobile", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true } },
  ],
});
