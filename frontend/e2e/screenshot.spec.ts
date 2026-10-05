import { test, expect, type Page, type Request } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";

/* Screenshot verification ("تحقق من صورة"). Test images are drawn at run time in the browser from the quotes in
   src/examples.json (generated from the verified corpus): nothing is typed from memory and no image file is stored
   in the repository. Malformed files are built byte by byte below. */

const SHOTS = "../docs/screenshots/redesign";
const shot = async (page: Page, name: string) => {
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-${name}.png`, fullPage: true });
};
const EX = Object.fromEntries(
  (JSON.parse(readFileSync(new URL("../src/examples.json", import.meta.url), "utf8")) as
    { examples: { id: string; quote: string; claim: string }[] }).examples.map((e) => [e.id, e]));
const isOcrAsset = (url: URL) => url.pathname.startsWith("/ocr/");

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
  expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}
async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over).toBeLessThanOrEqual(1);
}

type Draw = { size?: number; width?: number; bg?: string; fg?: string; noise?: boolean; type?: "image/png" | "image/jpeg" | "image/webp" };

/** A screenshot-like image of Arabic lines, drawn with the site's Naskh font. Returns the encoded bytes. */
async function drawImage(page: Page, lines: string[], o: Draw = {}): Promise<Buffer> {
  const b64 = await page.evaluate(async ({ lines, o }) => {
    const size = o.size ?? 30;
    await document.fonts.load(`${size}px "Noto Naskh Arabic"`);
    const W = o.width ?? 900, lh = size * 1.9, pad = 40;
    const c = document.createElement("canvas");
    c.width = W;
    c.height = Math.max(1, Math.round(pad * 2 + lh * lines.length));
    const x = c.getContext("2d")!;
    x.fillStyle = o.bg ?? "#ffffff";
    x.fillRect(0, 0, c.width, c.height);
    if (o.noise) {
      let seed = 7;
      const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
      for (let i = 0; i < 5000; i++) { x.fillStyle = `rgba(90,60,30,${rnd() * 0.3})`; x.fillRect(rnd() * W, rnd() * c.height, 2, 2); }
    }
    x.fillStyle = o.fg ?? "#111111";
    x.font = `${size}px "Noto Naskh Arabic"`;
    x.direction = "rtl";
    x.textAlign = "right";
    x.textBaseline = "top";
    lines.forEach((l, i) => x.fillText(l, W - pad, pad + i * lh));
    return c.toDataURL(o.type ?? "image/png", 0.92).split(",")[1];
  }, { lines, o });
  return Buffer.from(b64, "base64");
}

/** Every request the page makes; used to prove the image never leaves the browser. */
function watchRequests(page: Page): Request[] {
  const seen: Request[] = [];
  page.on("request", (r) => seen.push(r));
  return seen;
}
function assertNothingUploaded(reqs: Request[], base: string) {
  const origin = new URL(base).origin;
  for (const r of reqs) {
    const u = new URL(r.url());
    if (u.protocol === "blob:" || u.protocol === "data:") continue;
    // only this site (incl. its /ocr/ engine files) and the Tibyan API; no third party, no CDN
    expect([origin, "http://localhost:8000", "http://127.0.0.1:8000"]).toContain(u.origin);
    if (r.method() !== "GET") {
      expect(u.pathname).toBe("/api/v1/analyze");
      expect(r.headers()["content-type"]).toContain("application/json");
      const body = r.postData() ?? "";
      expect(body.length).toBeLessThan(10_000);
      expect(Object.keys(JSON.parse(body)).sort()).toEqual(["claim", "language", "quote"]);
    }
  }
}

async function openImageTab(page: Page) {
  await page.goto("/");
  await page.getByRole("tab", { name: "صورة" }).click();
  await expect(page.locator("#panel-image")).toBeVisible();
}
async function upload(page: Page, name: string, buffer: Buffer, mimeType = "image/png") {
  await page.locator("#image-input").setInputFiles({ name, mimeType, buffer });
}
async function waitReview(page: Page) {
  await expect(page.locator("[data-ocr-review]")).toBeVisible({ timeout: 60_000 });
}
const arabicKey = (s: string) => s.replace(/[ً-ْٰـ]/g, "").replace(/[أإآٱ]/g, "ا")
  .replace(/[ىئ]/g, "ي").replace(/[^ء-ي ]+/g, " ").replace(/\s+/g, " ").trim();

// ---------------------------------------------------------------- input method

// Keep in sync with frontend/src/features.ts. While the «صورة» tab is hidden, only the "absent" check runs.
const IMAGE_MODE_ENABLED = false;

test("image input is hidden: no «صورة» tab, no image panel, typed input works", async ({ page }) => {
  test.skip(IMAGE_MODE_ENABLED, "the image tab is enabled; its own tests below cover it");
  await page.goto("/");
  await expect(page.locator("#tab-image, #panel-image, [role='tablist']")).toHaveCount(0);
  await expect(page.getByText("صورة", { exact: true })).toHaveCount(0);
  await expect(page.locator("#quote")).toBeVisible();
  await page.goto("/methodology");
  await expect(page.getByText("التحقق من صورة")).toHaveCount(0);
});

test.beforeEach(({}, info) => {
  test.skip(!IMAGE_MODE_ENABLED && !info.title.startsWith("image input is hidden"),
    "the «صورة» tab is hidden (frontend/src/features.ts: IMAGE_MODE_ENABLED = false)");
});

test("input tabs: text is the default, image tab is keyboard reachable, panels switch", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "نص" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#quote")).toBeVisible();
  await expect(page.locator("#panel-image")).toBeHidden();
  await page.getByRole("tab", { name: "نص" }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("tab", { name: "صورة" })).toBeFocused();
  await expect(page.getByRole("tab", { name: "صورة" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "اختيار صورة" })).toBeVisible();
  await expect(page.locator("#panel-image")).toContainText("لا تُرفع الصورة إلى الخادم");
  await page.keyboard.press("Home");
  await expect(page.locator("#quote")).toBeVisible();
  await axe(page);
});

// ---------------------------------------------------------------- the main flow

test("clear screenshot: extract, review, confirm, same pipeline -> EXACT; nothing uploaded", async ({ page, baseURL }) => {
  const reqs = watchRequests(page);
  await openImageTab(page);
  await upload(page, "screenshot.png", await drawImage(page, [`«${EX.exact.quote}»`]));
  await waitReview(page);
  await expect(page.locator("#ocr-review-h")).toBeFocused();
  await expect(page.locator("[data-file-name]")).toHaveText("screenshot.png");
  await expect(page.locator(".file-preview")).toBeVisible();
  await expect(page.locator("[data-ocr-quality]")).toContainText("جودة استخراج النص:");
  expect(arabicKey(await page.inputValue("#ocr-quote"))).toBe(arabicKey(EX.exact.quote));
  // never auto-submitted: nothing was sent before the visitor confirms
  expect(reqs.filter((r) => r.url().includes("/api/v1/analyze"))).toHaveLength(0);
  await page.fill("#ocr-claim", EX.exact.claim);
  await page.getByRole("button", { name: "متابعة التحقق" }).click();
  await expect(page.locator("article.result")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "EXACT");
  await expect(page.locator("[data-input-source='image']")).toContainText("الصورة نفسها ليست دليلًا");
  // the comparison lives in the collapsed "النص والسياق" group
  await page.locator("article.result details").evaluateAll((ds) => ds.forEach((d) => { (d as HTMLDetailsElement).open = true; }));
  await expect(page.locator("[data-diff-summary]").first()).toBeVisible();
  assertNothingUploaded(reqs, baseURL!);
  await noHorizontalScroll(page);
  await axe(page);
});

test("quote + claim in one image: the claim is suggested, both are editable, the edited text is what is sent", async ({ page, baseURL }) => {
  const reqs = watchRequests(page);
  await openImageTab(page);
  const claim = "يقول بعضهم إن هذه الآية تأمر بالقتال مطلقا";
  await upload(page, "post.png", await drawImage(page, [claim, `لقوله تعالى: ﴿${EX.partial.quote}﴾`]));
  await waitReview(page);
  expect(arabicKey(await page.inputValue("#ocr-quote"))).toBe(arabicKey(EX.partial.quote));
  expect(arabicKey(await page.inputValue("#ocr-claim"))).toBe(arabicKey(claim));
  await expect(page.locator("#ocr-claim-tag")).toHaveText("الادعاء المقترح من الصورة");
  await page.fill("#ocr-quote", EX.partial.quote);
  await page.fill("#ocr-claim", EX.partial.claim);
  const sent = page.waitForRequest((r) => r.url().endsWith("/api/v1/analyze") && r.method() === "POST");
  await page.getByRole("button", { name: "متابعة التحقق" }).click();
  const body = JSON.parse((await sent).postData() ?? "{}");
  expect(body).toEqual({ quote: EX.partial.quote, claim: EX.partial.claim, language: "ar" });
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "PARTIAL", { timeout: 15_000 });
  // the text tab now holds the same confirmed text: one form, one pipeline
  await page.getByRole("tab", { name: "نص" }).click();
  await expect(page.locator("#quote")).toHaveValue(EX.partial.quote);
  assertNothingUploaded(reqs, baseURL!);
});

test("several quotes in one image: the visitor chooses one", async ({ page }) => {
  await openImageTab(page);
  await upload(page, "three.png", await drawImage(page, [`«${EX.exact.quote}»`, `و«${EX.ambiguous.quote}»`, `و«${EX.hadith.quote}»`]));
  await waitReview(page);
  await expect(page.locator(".cand-pick legend")).toHaveText("وجدنا ٣ نصوص محتملة");
  await expect(page.locator(".cand-option")).toHaveCount(3);
  expect(arabicKey(await page.inputValue("#ocr-quote"))).toBe(arabicKey(EX.exact.quote));
  await page.locator(".cand-option").nth(1).click();
  expect(arabicKey(await page.inputValue("#ocr-quote"))).toBe(arabicKey(EX.ambiguous.quote));
  await axe(page);
  await shot(page, "18-screenshot-review");
});

test("multi-line quote: lines are joined in reading order (RTL)", async ({ page }) => {
  await openImageTab(page);
  const w = EX.hadith.quote.split(" ");
  await upload(page, "lines.png", await drawImage(page, [`«${w.slice(0, 3).join(" ")}`, `${w.slice(3).join(" ")}»`]));
  await waitReview(page);
  const got = arabicKey(await page.inputValue("#ocr-quote")).split(" ");
  expect(got[0]).toBe(arabicKey(w[0]));
  expect(got.join(" ")).toBe(arabicKey(EX.hadith.quote));
});

test("small font, dark background and noisy background are still read; quality shown as OCR quality only", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "OCR robustness once");
  test.setTimeout(120_000);
  await openImageTab(page);
  for (const [name, o] of [
    ["small.png", { size: 15, width: 520 }],
    ["dark.png", { bg: "#15202b", fg: "#e7e9ea" }],
    ["noisy.jpg", { noise: true, type: "image/jpeg" as const }],
  ] as const) {
    await upload(page, name, await drawImage(page, [`«${EX.hadith.quote}»`], o), name.endsWith(".jpg") ? "image/jpeg" : "image/png");
    await waitReview(page);
    const got = arabicKey(await page.inputValue("#ocr-quote")).split(" ");
    const want = arabicKey(EX.hadith.quote).split(" ");
    const same = want.filter((x, i) => got[i] === x).length;
    expect(same / want.length, name).toBeGreaterThanOrEqual(0.7);       // the visitor corrects the rest
    await expect(page.locator("[data-ocr-quality]")).toHaveAttribute("data-ocr-quality", /good|fair|poor/);
    await expect(page.locator(".ocr-quality")).not.toContainText("%");
    await page.getByRole("button", { name: "إزالة الصورة" }).click();
  }
});

test("WEBP and JPEG screenshots are accepted", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "formats once");
  await openImageTab(page);
  for (const [name, type] of [["shot.webp", "image/webp"], ["shot.jpeg", "image/jpeg"]] as const) {
    await upload(page, name, await drawImage(page, [`«${EX.exact.quote}»`], { type }), type);
    await waitReview(page);
    await page.getByRole("button", { name: "إزالة الصورة" }).click();
  }
});

test("drag and drop, and paste from the clipboard, use the same checks and review", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "pointer input once");
  await openImageTab(page);
  const b64 = (await drawImage(page, [`«${EX.exact.quote}»`])).toString("base64");
  const dt = await page.evaluateHandle((b64) => {
    const dt = new DataTransfer();
    dt.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], "dropped.png", { type: "image/png" }));
    return dt;
  }, b64);
  await page.dispatchEvent("[data-dropzone]", "dragover", { dataTransfer: dt });
  await expect(page.locator("[data-dropzone]")).toHaveClass(/is-drag/);
  await page.dispatchEvent("[data-dropzone]", "drop", { dataTransfer: dt });
  await waitReview(page);
  await expect(page.locator("[data-file-name]")).toHaveText("dropped.png");
  await page.getByRole("button", { name: "إزالة الصورة" }).click();
  await page.evaluate((b64) => {
    const dt = new DataTransfer();
    dt.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], "image.png", { type: "image/png" }));
    document.body.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }));
  }, b64);
  await waitReview(page);
  await expect(page.locator("[data-file-name]")).toHaveText("image.png");
  expect(page.url()).toMatch(/\/$/);                    // still on the page
});

test("blank image: no text found, typed input offered", async ({ page }) => {
  await openImageTab(page);
  await upload(page, "blank.png", await drawImage(page, [""]));
  await expect(page.locator("[data-ocr-error='NO_TEXT']")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("[data-ocr-error='NO_TEXT']")).toContainText("لم نعثر على نص عربي واضح في الصورة.");
  await page.getByRole("button", { name: "اكتب النص يدويًا" }).click();
  await expect(page.getByRole("tab", { name: "نص" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#quote")).toBeVisible();
});

// ---------------------------------------------------------------- file checks (no OCR is started)

function pngHeader(width: number, height: number, tail: Buffer = Buffer.alloc(0)): Buffer {
  const ihdr = Buffer.alloc(25);
  ihdr.writeUInt32BE(13, 0);
  ihdr.write("IHDR", 4, "ascii");
  ihdr.writeUInt32BE(width, 8);
  ihdr.writeUInt32BE(height, 12);
  ihdr.set([8, 6, 0, 0, 0], 16);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), ihdr, tail]);
}

const BAD_FILES: [string, string, string, () => Buffer][] = [
  ["EMPTY", "empty.png", "image/png", () => Buffer.alloc(0)],
  ["UNSUPPORTED_TYPE", "anim.gif", "image/gif", () => Buffer.concat([Buffer.from("GIF89a"), Buffer.alloc(64, 1)])],
  ["UNSUPPORTED_TYPE", "vector.svg", "image/svg+xml", () => Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')],
  ["UNSUPPORTED_TYPE", "doc.pdf", "application/pdf", () => Buffer.from("%PDF-1.7\n%âãÏÓ\n1 0 obj\n")],
  ["NOT_AN_IMAGE", "notes.png", "image/png", () => Buffer.from("this is plain text with a .png name")],
  ["NOT_AN_IMAGE", "run.png", "image/png", () => Buffer.concat([Buffer.from("MZ"), Buffer.alloc(200, 0x90)])],
  ["TOO_LARGE", "huge.png", "image/png", () => pngHeader(1000, 1000, Buffer.alloc(8 * 1024 * 1024))],
  ["DIMENSIONS_TOO_LARGE", "bomb.png", "image/png", () => pngHeader(20000, 20000, Buffer.alloc(64))],
  ["DIMENSIONS_TOO_LARGE", "wide.png", "image/png", () => pngHeader(9000, 50, Buffer.alloc(64))],
  ["DIMENSIONS_TOO_SMALL", "dot.png", "image/png", () => pngHeader(8, 8, Buffer.alloc(64))],
  ["CORRUPT", "broken.png", "image/png", () => pngHeader(400, 300, Buffer.from("not really compressed pixel data"))],
];

test("file checks: type by content, size, dimensions before decoding, corrupt files; OCR never starts", async ({ page, baseURL }, info) => {
  test.skip(info.project.name !== "desktop", "file checks once");
  const reqs = watchRequests(page);
  await openImageTab(page);
  for (const [code, name, mime, make] of BAD_FILES) {
    await upload(page, name, make(), mime);
    await expect(page.locator(`[data-image-error='${code}']`), name).toContainText(name);
    await expect(page.locator("[data-ocr-review]")).toHaveCount(0);
  }
  // a JPEG that claims to be a PNG
  const jpeg = await drawImage(page, ["نص"], { type: "image/jpeg" });
  await upload(page, "photo.png", jpeg, "image/png");
  await expect(page.locator("[data-image-error='TYPE_MISMATCH']")).toBeVisible();
  expect(reqs.some((r) => isOcrAsset(new URL(r.url())))).toBe(false);      // the engine was never loaded
  assertNothingUploaded(reqs, baseURL!);
  await axe(page);
});

test("hostile file names are shown as text only and go nowhere", async ({ page, baseURL }, info) => {
  test.skip(info.project.name !== "desktop", "once");
  const reqs = watchRequests(page);
  let dialog = false;
  page.on("dialog", (d) => { dialog = true; void d.dismiss(); });
  await openImageTab(page);
  const img = await drawImage(page, [`«${EX.exact.quote}»`]);
  for (const [name, shown] of [
    ['<img src=x onerror=alert(1)>.png', '<img src=x onerror=alert(1)>.png'],
    ["../../../etc/passwd.png", "passwd.png"],
    ["..\\..\\windows\\win.ini.png", "win.ini.png"],
    ["invoice‮gnp.exe.png", "invoicegnp.exe.png"],
  ]) {
    await upload(page, name, img);
    await waitReview(page);
    await expect(page.locator("[data-file-name]")).toHaveText(shown);
    await expect(page.locator("img[src='x']")).toHaveCount(0);
    await page.getByRole("button", { name: "إزالة الصورة" }).click();
  }
  expect(dialog).toBe(false);
  for (const r of reqs) expect(r.url()).not.toContain("passwd");
  assertNothingUploaded(reqs, baseURL!);
});

// ---------------------------------------------------------------- failures and cleanup

test("OCR engine failure: clear error, retry, typed input still works", async ({ page }) => {
  await page.route(isOcrAsset, (route) => route.abort("failed"));
  await openImageTab(page);
  await upload(page, "shot.png", await drawImage(page, [`«${EX.exact.quote}»`]));
  await expect(page.locator("[data-ocr-error='ENGINE']")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("alert")).toContainText("تعذّر تشغيل محرك استخراج النص.");
  await page.unroute(isOcrAsset);
  await page.getByRole("button", { name: "إعادة المحاولة" }).click();
  await waitReview(page);
  await page.getByRole("tab", { name: "نص" }).click();
  await page.getByRole("button", { name: "اقتباس كامل" }).click();
  await page.getByRole("button", { name: "تحقق من السياق" }).click();
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "EXACT", { timeout: 15_000 });
});

test("remove: preview released, state cleared, a new image can be chosen", async ({ page }) => {
  await openImageTab(page);
  await upload(page, "shot.png", await drawImage(page, [`«${EX.exact.quote}»`]));
  await waitReview(page);
  const src = await page.locator(".file-preview").getAttribute("src");
  expect(src).toMatch(/^blob:/);
  await page.getByRole("button", { name: "إزالة الصورة" }).click();
  await expect(page.locator("[data-dropzone]")).toBeVisible();
  await expect(page.locator("[data-ocr-review], .file-card")).toHaveCount(0);
  const fetched = await page.evaluate((u) => fetch(u!).then(() => "still there", () => "released"), src);
  expect(fetched).toBe("released");
  expect(await page.locator("#image-input").evaluate((el) => (el as HTMLInputElement).files?.length ?? 0)).toBe(0);
  await upload(page, "again.png", await drawImage(page, [`«${EX.hadith.quote}»`]));
  await waitReview(page);
});

test("review is required: empty fields are rejected with the same rules as typed text", async ({ page }) => {
  await openImageTab(page);
  await upload(page, "shot.png", await drawImage(page, [`«${EX.exact.quote}»`]));
  await waitReview(page);
  await page.fill("#ocr-quote", "hello world");
  await page.fill("#ocr-claim", "");
  await page.getByRole("button", { name: "متابعة التحقق" }).click();
  await expect(page.locator("#ocr-quote-err")).toContainText("نص عربي");
  await expect(page.locator("#ocr-claim-err")).toBeVisible();
  await expect(page.locator("#ocr-quote")).toBeFocused();
  await expect(page.locator("article.result")).toHaveCount(0);
});

// ---------------------------------------------------------------- look and layout

test("dark mode and narrow screens: review panel readable, no horizontal scroll, no a11y violations", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await openImageTab(page);
  await noHorizontalScroll(page);
  await upload(page, "post.png", await drawImage(page, ["يقول بعضهم إن هذه الآية تأمر بالقتال مطلقا", `لقوله تعالى: ﴿${EX.partial.quote}﴾`]));
  await waitReview(page);
  await noHorizontalScroll(page);
  await axe(page);
  await shot(page, "19-screenshot-review-dark");
});
