# Privacy (2026-10-03)

Tibyan has no accounts and keeps no user content. This page lists every piece of data the product handles, where it goes, and how long it lives. It covers the two ways of entering a quote: typing it («نص») and taking it from a screenshot («صورة»).

## 1. Typed text (quote and claim)

| Data | Where it goes | Kept? |
|---|---|---|
| Quote and claim | One `POST /api/v1/analyze` request to the Tibyan backend, as JSON `{quote, claim, language}` | **No.** Held in memory for the request only. Not written to disk or a database |
| Server log line | Request id, status codes, ids of the passages used, counts, timings | Yes (operator's log retention). **Never the quote or claim text** (`LOG_RAW_INPUT=false` by default; tested by `test_e2e_api_real.py::test_raw_input_never_logged`) |
| Language model (only if an operator configured one) | The quote, claim and the backend evidence objects, sent to that provider's API for claim analysis, under that provider's terms | Not by Tibyan; see the provider's own policy. Without a key nothing is sent anywhere |
| Response | Returned to the browser and shown; `Cache-Control: no-store` | Lives in the page until it is closed or a new check starts |

## 2. Screenshot input («تحقق من صورة»)

**The image never leaves the visitor's device.** Text is extracted inside the browser with tesseract.js (WebAssembly). The backend has no upload route, no OCR code, and no way to receive an image: image bodies sent to the API are refused (413 / 415 / 422 / 404) before any processing (`backend/tests/test_no_image_upload.py`).

| Step | What happens to the data | Lifetime |
|---|---|---|
| File chosen, dropped or pasted | Read into browser memory. Its name is shown as plain text (control and bidirectional characters removed); the name is never sent | Until the visitor removes the image, chooses another one or leaves the page |
| Checks | Size, real file signature, type, header dimensions; then decoded to pixels (`ImageBitmap`) | The bitmap is closed when the image is removed or replaced |
| Preview | A re-encoded copy of the pixels (no EXIF or other metadata) as a `blob:` URL that only this page can read | Revoked on remove, on replace, and when the page is left (`URL.revokeObjectURL`; checked by an E2E test) |
| Text extraction | A grey-scale copy on an off-screen canvas is passed to a Web Worker running the OCR engine. Metadata such as camera, location or time (EXIF) is never read or passed on | The worker is terminated after each image and the canvas is released |
| OCR engine files | `/ocr/worker.min.js`, `/ocr/core/*.wasm.js`, `/ocr/lang/ara.traineddata.gz` are downloaded **from the Tibyan site itself**, never from a CDN. The model is not stored in IndexedDB (`cacheMethod: "none"`); the browser's normal HTTP cache may keep these public program files | n/a (no user data) |
| Review | The extracted text, a suggested quote and a suggested claim are shown for the visitor to edit | In the page only |
| Verification | Only after the visitor presses «متابعة التحقق»: the confirmed quote and claim go through the same JSON request as typed text (§1). Nothing identifies that the text came from an image | As §1 |

Not done: no analytics, no telemetry, no error reporting service, no third-party request of any kind during screenshot processing. The screenshot browser tests record the requests made while images are processed and fail if any goes to another origin or carries anything other than `{quote, claim, language}` JSON.

## 3. Browser storage
- `localStorage` keeps one value: the light/dark theme choice.
- Nothing else is stored in cookies, `localStorage`, `sessionStorage` or IndexedDB by Tibyan.

## 4. Operator responsibilities
- Keep `LOG_RAW_INPUT=false` in production.
- If a language model is configured, tell users which provider receives the quote and claim.
- If a reverse proxy or host adds its own request logging, its retention applies to request metadata (never to images, which are not sent).

## 5. Verifying these statements
- Backend: `backend/tests/test_no_image_upload.py`, `test_e2e_api_real.py::test_raw_input_never_logged`.
- Browser: `frontend/e2e/screenshot.spec.ts` (requests watched while images are processed; preview released on remove; file names never sent).
