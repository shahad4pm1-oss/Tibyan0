import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const SHOTS = "../docs/screenshots/redesign";
const shot = async (page: Page, name: string) => {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-${name}.png`, fullPage: true });
};

/** Lets finite animations and transitions (result fade-in, theme change) finish first, so colour contrast is
 *  measured on the settled page rather than on a half-faded frame. Infinite ones (spinners) are ignored. */
async function settle(page: Page) {
  await page.evaluate(() => Promise.all(document.getAnimations()
    .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
    .map((a) => a.finished.catch(() => undefined))));
}

async function axe(page: Page) {
  await settle(page);
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ") + " " + (n.any[0]?.message ?? "")).join(" | ")}`)).toEqual([]);
}

async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over).toBeLessThanOrEqual(1);
}

/** Examples fill the form; the visitor then submits through the real pipeline. */
async function runExample(page: Page, label: string) {
  await page.goto("/");
  await page.getByRole("button", { name: label }).click();
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator("article.result")).toBeVisible({ timeout: 15_000 });
  // the report opens as a summary card with every detail group collapsed; tests then expand them to read the detail
  await expect(page.locator("article.result details[open]")).toHaveCount(0);
  await expandAll(page);
}

/** Opens every collapsed group, evidence row and disclosure of the result. */
async function expandAll(page: Page) {
  await page.locator("article.result details").evaluateAll((ds) => ds.forEach((d) => { (d as HTMLDetailsElement).open = true; }));
}

const reportIds = (page: Page, level: "h2" | "h3" = "h2") =>
  page.locator(`article.result section ${level}[id^='h-']`).evaluateAll((hs) => hs.map((h) => h.id));

test("home: RTL, landmarks, skip link, hero, empty state, no a11y violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("تحقق من النصوافهم سياقه");
  await expect(page.getByText("ستظهر نتيجة التحقق هنا")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip")).toBeFocused();
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "01-home");
});

test("hero CTA moves focus to the quote field", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "ابدأ التحقق" }).click();
  await expect(page.locator("#quote")).toBeFocused();
});

test("input validation: empty and non-Arabic", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator("#quote-err")).toBeVisible();
  await expect(page.locator("#quote")).toBeFocused();
  await expect(page.locator("#quote")).toHaveAttribute("aria-invalid", "true");
  await page.fill("#quote", "hello world");
  await page.fill("#claim", "x claim");
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator("#quote-err")).toContainText("نص عربي");
  await shot(page, "02-validation");
});

test("example fills the form without submitting", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  await expect(page.locator("#quote")).not.toHaveValue("");
  await expect(page.locator("#claim")).not.toHaveValue("");
  await expect(page.locator("article.result")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "تحقق من السياق" })).toBeFocused();
});

test("exact Quran quote -> EXACT, report order, sacred-text treatment, no-LLM message, AI-failed banner", async ({ page }) => {
  await runExample(page, "اقتباس كامل");
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "EXACT");
  await expect(page.locator(".status-title")).toHaveText("مطابق");
  await expect(page.locator("[data-claim-status]")).toHaveText("تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً");
  await expect(page.locator(".ai-box")).toHaveCount(0);
  await expect(page.locator("[data-relation]")).toHaveCount(0);
  // the AI step is never hidden silently: a visible error banner in the summary card
  await expect(page.locator(".summary [data-ai-failed]")).toHaveCount(1);
  await expect(page.locator("[data-ai-failed]").first()).toContainText("AI Analysis Failed");
  // summary card, then three groups; the detail blocks live inside the groups
  expect(await reportIds(page)).toEqual(["h-quote", "h-text", "h-ev", "h-lim"]);
  expect(await reportIds(page, "h3")).toEqual(["h-src", "h-ctx", "h-diff", "h-map", "h-limits", "h-refs"]);
  await expect(page.locator("[data-diff-summary='VERBATIM']")).toBeVisible();
  await expect(page.locator(".scripture .original")).toContainText("ٱلۡحَمۡدُ");
  const font = await page.locator(".original").evaluate((el) => getComputedStyle(el).fontFamily);
  expect(font).toContain("Uthmanic");
  await expect(page.locator(".ctx-matched")).toBeVisible();
  await expect(page.locator(".ev-card")).not.toHaveCount(0);
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "03-quran-exact");
});

test("Quran diff: a changed word is shown against the closest ayah, without attribution", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  const exact = await page.locator("#quote").inputValue();
  const words = exact.trim().split(/\s+/);
  await page.fill("#quote", [...words.slice(0, -1), words[words.length - 1].replace(/ين$/, "ون")].join(" "));
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "NEAR_MATCH_UNCONFIRMED", { timeout: 15_000 });
  await expect(page.locator("#h-diff")).toHaveCount(0);                 // no definitive diff without a source
  const cand = page.locator("[data-candidate-comparison]").first();
  await cand.locator("summary").click();
  await expect(cand.locator("[data-diff-summary='SUBSTITUTED_WORDS']")).toBeVisible();
  await expect(cand.locator("[data-diff-kind='SUBSTITUTED']")).toContainText("كتبتَ");
  await expect(cand.locator("[data-tok='SUBSTITUTED'] .sr-only").first()).toHaveText("كلمة مختلفة: ");
  await axe(page);
  await shot(page, "16-quran-diff-near-match");
});

test("evidence map: nodes, evidence chips that reach the evidence cards, neutral context relevance", async ({ page }) => {
  await runExample(page, "اقتباس مقتطع");
  const map = page.locator("section[aria-labelledby='h-map']");
  await expect(map).toBeVisible();
  await expect(map.locator("[data-node-kind='matched']")).toHaveCount(1);
  await expect(map.locator("[data-node-kind='preceding_context']")).not.toHaveCount(0);
  await expect(map.locator("[data-node-kind='matched'] .seg-quoted")).toHaveCount(1);
  await expect(map.locator("[data-node-kind='matched'] .seg-near_context")).not.toHaveCount(0);
  // every evidence id in the map exists as an evidence item; nothing invented
  const mapIds = await map.locator("[data-step='evidence'] [data-map-evidence]").allInnerTexts();
  const evIds = await page.locator(".ev-card .ev-id").allInnerTexts();
  expect(mapIds.slice(0, evIds.length)).toEqual(evIds);
  await map.locator("[data-node-kind='matched'] [data-map-evidence='E1']").click();
  await expect(page.locator("#ev-E1")).toBeFocused();
  await expect(map.locator("[data-context-relevance]")).toHaveAttribute("data-context-relevance", "UNDETERMINED");
  await expect(map).toContainText("حقيقة نصية");
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "17-evidence-map");
});

test("evidence rows: long commentary is clipped, shown in full on demand, without raw print markers", async ({ page }) => {
  await runExample(page, "اقتباس مقتطع");
  const more = page.locator(".ev-card .more-btn");
  test.skip((await more.count()) === 0, "no long commentary evidence in this corpus build");
  await expect(page.locator("[data-tafsir-clipped='true']")).toHaveCount(1);
  await more.first().click();
  await expect(more.first()).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("[data-tafsir-clipped='true']")).toHaveCount(0);
  const text = await page.locator(".tafsir-text").first().innerText();
  expect(text).not.toMatch(/&;|\* \* \*/);
  await noHorizontalScroll(page);
});

test("evidence map: hadith has no neighbouring records; AMBIGUOUS and NOT_FOUND have no map", async ({ page }) => {
  await runExample(page, "حديث من الصحيحين");
  const map = page.locator("section[aria-labelledby='h-map']");
  await expect(map.locator("[data-node-kind]")).toHaveCount(1);
  await expect(map).toContainText("لا تُعرض الأحاديث المجاورة");
  await runExample(page, "عبارة متكررة");
  await expect(page.locator("#h-map")).toHaveCount(0);
  await runExample(page, "نص غير موجود");
  await expect(page.locator("#h-map")).toHaveCount(0);
});

test("hadith diff: honorific and punctuation are normalization-only, partial quote", async ({ page }) => {
  await runExample(page, "حديث من الصحيحين");
  await expect(page.locator("#h-diff")).toBeVisible();
  await expect(page.locator("[data-diff-summary='PARTIAL_QUOTE']")).toBeVisible();
  await expect(page.locator("[data-diff-summary='SUBSTITUTED_WORDS'], [data-diff-summary='MISSING_WORDS']")).toHaveCount(0);
  await noHorizontalScroll(page);
});

test("partial quote -> PARTIAL with preceding / matched / following context", async ({ page }) => {
  await runExample(page, "اقتباس مقتطع");
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "PARTIAL");
  await expect(page.locator("#h-ctx")).toBeVisible();
  await expect(page.locator(".reading .ayah")).not.toHaveCount(0);
  await expect(page.locator(".ctx-label").first()).toBeVisible();
  await noHorizontalScroll(page);
  await shot(page, "04-quran-partial");
});

test("ambiguous quote -> possible matches with references, no attribution", async ({ page }) => {
  await runExample(page, "عبارة متكررة");
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "AMBIGUOUS");
  await expect(page.getByText("وجدنا أكثر من موضع محتمل").first()).toBeVisible();
  await expect(page.locator("#h-alts")).toBeVisible();
  await expect(page.locator(".alts li")).not.toHaveCount(0);
  await expect(page.locator("#h-orig, #h-src")).toHaveCount(0);
  await expect(page.locator("[data-source-none]")).toHaveText("لم يتم اعتماد نسبة نهائية للنص.");
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "05-ambiguous");
});

test("not found -> calm state, next steps, honest scope note, nothing attributed", async ({ page }) => {
  await runExample(page, "نص غير موجود");
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "NOT_FOUND");
  await expect(page.locator(".status-title")).toHaveText("لم نعثر على مصدر كافٍ");
  await expect(page.locator(".status-detail")).toContainText("عدم العثور لا يعني");
  await expect(page.locator("#h-next")).toBeVisible();
  await expect(page.locator(".next-steps li")).toHaveCount(3);
  await expect(page.locator("#h-orig, #h-ctx, #h-ev")).toHaveCount(0);
  await expect(page.getByText("مختلق")).toHaveCount(0);
  await axe(page);
  await shot(page, "06-not-found");
});

test("hadith quote -> hadith source card, Naskh text (never the Quran font), no verdict", async ({ page }) => {
  await runExample(page, "حديث من الصحيحين");
  await expect(page.locator("article.result")).toHaveAttribute("data-source-type", "hadith");
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "PARTIAL");
  const orig = page.locator("section[aria-labelledby='h-orig']");
  await expect(orig.locator(".hadith .hadith-text").first()).toContainText("إنما الأعمال بالنيات");
  await expect(orig.locator(".quran")).toHaveCount(0);
  const font = await orig.locator(".hadith-text").first().evaluate((el) => getComputedStyle(el).fontFamily);
  expect(font).not.toContain("Uthmanic");
  expect(font).toContain("Naskh");
  await expect(page.locator(".source-ref")).toHaveText("الحديث رقم ١");
  await expect(page.locator("[data-grading]")).toHaveAttribute("data-grading", "SCIENTIFIC_PACKAGE_SAHIHAYN_RULE");
  await expect(page.locator("[data-claim-status]")).toHaveText("تحليل الادعاء غير مفعّل لهذا النوع من المصادر بعد");
  await expect(page.locator(".ai-box")).toHaveCount(0);
  await expect(page.locator("section[aria-labelledby='h-ctx']")).toContainText("لا تُعرض الأحاديث المجاورة");
  await expect(page.locator("[data-warning='HADITH_LIMITED_PRODUCTION']")).toContainText("تشغيل محدودة");
  await expect(page.locator("[data-crosscheck]")).toHaveAttribute("data-crosscheck", "PENDING");
  await expect(page.locator("[data-edition-reuse]")).toHaveAttribute("data-edition-reuse", "PENDING_VERIFICATION");
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "07-hadith");
});

test("saying not in the approved sources -> NOT_FOUND, nothing attributed", async ({ page }) => {
  await runExample(page, "قول متداول");
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "NOT_FOUND");
  await expect(page.locator(".status-detail")).toContainText("صحيحي البخاري ومسلم");
  await expect(page.locator(".hadith, #h-orig")).toHaveCount(0);
});

test("personal-fatwa claim -> calm specialist panel (system text, not AI)", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  await page.fill("#claim", "هل يجوز لي أن أطلق زوجتي الآن");
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator(".specialist")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".specialist h3")).toHaveText("هذه المسألة تحتاج مراجعة مختص");
  await expect(page.locator(".specialist")).toContainText("لا يصدر تِبيان فتاوى شخصية");
  await expect(page.locator(".ai-box")).toHaveCount(0);
  await axe(page);
  await shot(page, "08-specialist");
});

test("the package glossary sample is not part of the product: no terms block, no source card", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  await page.fill("#claim", "هذه الآية في التوحيد");
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator("article.result")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("[data-term], #h-terms")).toHaveCount(0);
  await page.goto("/sources");
  await expect(page.locator("[data-source-id='quran']")).toBeVisible();
  await expect(page.locator("[data-source-id^='glossary']")).toHaveCount(0);
});

test("loading state: staged steps announced, LLM step marked unavailable, button disabled", async ({ page }) => {
  await page.route("**/api/v1/analyze", async (route) => {
    await new Promise((r) => setTimeout(r, 1200));
    await route.continue();
  });
  await page.goto("/");
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator(".loading[role=status]")).toBeVisible();
  await expect(page.locator(".steps-live li")).toHaveCount(5);
  await expect(page.locator(".steps-live li[data-state='off']")).toContainText("غير متاح حاليًا");
  await expect(page.getByRole("button", { name: "جارٍ التحقق…" })).toBeDisabled();
  await shot(page, "09-loading");
  await expect(page.locator("article.result")).toBeVisible({ timeout: 15_000 });
});

for (const [status, code, text] of [
  [500, "INTERNAL_ERROR", "حدث خطأ داخلي في الخادم."],
  [503, "CORPUS_NOT_AVAILABLE", "قاعدة المصادر غير متاحة حاليًا."],
  [429, "RATE_LIMITED", "وصلت إلى الحد المسموح من الطلبات."],
] as const) {
  test(`server failure ${status} ${code} -> clear Arabic error, no result`, async ({ page }) => {
    await page.route("**/api/v1/analyze", (route) =>
      route.fulfill({ status, contentType: "application/json",
        body: JSON.stringify({ request_id: "e2e00000-0000", error: { code, message_ar: "", message_en: "" } }) }));
    await runExampleExpectingError(page);
    await expect(page.getByRole("alert")).toContainText(text);
    await expect(page.locator("article.result")).toHaveCount(0);
  });
}

async function runExampleExpectingError(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
}

test("network failure -> NETWORK error", async ({ page }) => {
  await page.route("**/api/v1/analyze", (route) => route.abort("connectionrefused"));
  await runExampleExpectingError(page);
  await expect(page.getByRole("alert")).toContainText("تعذّر الوصول إلى خادم تبيان.");
});

test("methodology page: pipeline, LLM is not a source, limitations, no-LLM state", async ({ page }) => {
  await page.goto("/methodology");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("المنهجية والحدود");
  await expect(page.getByText("النموذج اللغوي ليس مصدرًا للمعلومة الشرعية.")).toBeVisible();
  await expect(page.locator(".pipeline li")).toHaveCount(7);
  await expect(page.locator(".concepts li")).toHaveCount(6);
  await expect(page.locator("#m-lim")).toBeVisible();
  await expect(page.locator("[data-llm-configured]")).toHaveAttribute("data-llm-configured", "false");
  await page.getByText("تفاصيل تقنية").click();
  await expect(page.locator(".steps-full li").first()).toBeVisible();
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "10-methodology");
});

test("evaluation page: coverage, measured metrics only, LLM pending", async ({ page }) => {
  await page.goto("/evaluation");
  await expect(page.locator("[data-llm-status]")).toHaveAttribute("data-llm-status", "PENDING_REAL_MODEL_VALIDATION");
  await expect(page.getByText("Pending real-model validation", { exact: false })).toBeVisible();
  await expect(page.getByText("ليست أداء نموذج")).toBeVisible();
  await expect(page.locator(".metric").first()).toBeVisible();
  await expect(page.locator(".metric-value", { hasText: "٦٢٣٦" })).toBeVisible();
  await expect(page.locator("#ev-hadith")).toBeVisible();
  await expect(page.locator("table").first()).toBeVisible();
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "11-evaluation");
});

test("sources page: integrated sources with hashes, no pending-sources list", async ({ page }) => {
  await page.goto("/sources");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("المصادر");
  for (const id of ["quran", "hadith:bukhari", "hadith:muslim"])
    await expect(page.locator(`[data-source-id='${id}']`)).toBeVisible();
  await expect(page.getByText(/^SHA-256 [0-9a-f]{64}$/).first()).toBeVisible();
  await expect(page.locator("[data-pending-source], #s-next")).toHaveCount(0);
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "12-sources");
});

test("client-side navigation, deep links and footer links", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "أقسام الموقع", exact: true });
  if (await nav.isVisible()) {
    await nav.getByRole("link", { name: "التقييم" }).click();
  } else {
    await page.getByRole("button", { name: "القائمة" }).click();
    await page.getByRole("dialog").getByRole("link", { name: "التقييم" }).click();
  }
  await expect(page).toHaveURL(/\/evaluation$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("التقييم");
  await page.goBack();
  await expect(page.locator("#quote")).toBeVisible();
  await page.getByRole("contentinfo").getByRole("link", { name: "المصادر" }).click();
  await expect(page).toHaveURL(/\/sources$/);
});

test("mobile menu: opens as a dialog, traps focus, closes on Escape", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "mobile only");
  await page.goto("/");
  const btn = page.getByRole("button", { name: "القائمة" });
  await btn.click();
  const dialog = page.getByRole("dialog", { name: "القائمة" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "إغلاق القائمة" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("link", { name: "المصادر" })).toBeFocused();
  await axe(page);
  await shot(page, "13-mobile-menu");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(btn).toBeFocused();
});

test("theme toggle: dark mode applies, persists across reloads, passes axe", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "التبديل إلى الوضع الداكن" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await axe(page);
  await shot(page, "14-dark-home");
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator("article.result")).toBeVisible({ timeout: 15_000 });
  await axe(page);
  await shot(page, "15-dark-quran-exact");
  await page.goto("/evaluation");
  await expect(page.locator(".metric").first()).toBeVisible();
  await axe(page);
  await page.getByRole("button", { name: "التبديل إلى الوضع الفاتح" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("system dark preference is followed when no choice is stored", async ({ browser }) => {
  const ctx = await browser.newContext({ colorScheme: "dark", locale: "ar" });
  const page = await ctx.newPage();
  await page.goto(test.info().project.use.baseURL + "/");
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(15, 21, 19)");
  await ctx.close();
});

test("copy actions copy the reference and evidence", async ({ page, context }, info) => {
  test.skip(info.project.name !== "desktop", "desktop only");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await runExample(page, "اقتباس كامل");
  await page.getByRole("button", { name: "نسخ النص مع الموضع" }).click();
  await expect(page.getByRole("button", { name: "نُسخ" }).first()).toBeVisible();
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  expect(clip).toContain("سورة");
  await page.getByRole("button", { name: "نسخ الدليل" }).first().click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("E1");
});

test("responsive: no horizontal scroll at 375 / 390 / 430 / 768 / 1024 / 1440", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "runs all widths once");
  test.setTimeout(120_000);
  for (const w of [375, 390, 430, 768, 1024, 1440]) {
    await page.setViewportSize({ width: w, height: 900 });
    for (const p of ["/", "/methodology", "/evaluation", "/sources"]) {
      await page.goto(p);
      await page.waitForLoadState("networkidle");
      await noHorizontalScroll(page);
    }
    for (const label of ["اقتباس كامل", "حديث من الصحيحين", "عبارة متكررة", "نص غير موجود"]) {
      await runExample(page, label);
      await noHorizontalScroll(page);
    }
    const small = await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll<HTMLElement>("main p, main li, main dd, main dt, main span"));
      return els.filter((e) => e.offsetParent && e.innerText.trim() && parseFloat(getComputedStyle(e).fontSize) < 12).length;
    });
    expect(small).toBe(0);
  }
});
