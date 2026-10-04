# Tibyan design system (premium UI v1)

The UI is meant to feel quiet, credible and precise. Source text leads, and AI output never looks more authoritative than the source.

The tokens live in `frontend/src/index.css` (`:root`, with dark values under `[data-theme="dark"]` and `prefers-color-scheme`). The components live in `frontend/src/components/ui.tsx`. Components use only the tokens, never their own raw values.

## Colour (light / dark)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--c-bg` | `#f3f4f1` | `#0f1513` | page background (warm grey) |
| `--c-surface` | `#fcfcfa` | `#151d1a` | panels, cards |
| `--c-ink` / `--c-ink-2` / `--c-ink-3` | `#18211f` / `#45504c` / `#5f6a66` | `#e8ece9` / `#bcc6c1` / `#9aa6a0` | text, secondary text, muted text (all AA on bg and surface) |
| `--c-primary` | `#0f4a43` | `#2f7d70` | deep emerald / teal: primary actions, current page |
| `--c-accent` | `#8f6115` | `#d9ac62` | amber: hadith marks and "limited" states only |
| success / warning / error / info | `#2b6642` / `#835600` / `#983a2f` / `#3a5864` | lighter steps | status, always paired with an icon and a label |
| `--c-quran-bg`, `--c-quran-frame` | ivory, sand frame | deep green, muted frame | Quran text field |
| `--c-hadith-bg`, `--c-hadith-rule` | warm paper, amber rule | dark paper, amber rule | hadith text |
| `--c-ai-bg`, `--c-ai-line` | cool grey-blue | dark slate | AI analysis (never green, never gold) |

Green is the brand colour. It appears on actions, links and the current page, and never as a background wash.

## Type

| Role | Family | Notes |
|---|---|---|
| Display: wordmark, hero, page titles, metric values | Reem Kufi | A geometric Kufi face, used only at large sizes |
| UI and body | IBM Plex Sans Arabic 400–700 | Body 16–17px, line-height 1.75 (reading 1.95) |
| Hadith text and quote field | Noto Naskh Arabic | Never used for Quran text |
| Quran text | KFGQPC Uthmanic Hafs v2.0 | Comes from the same verified package as the text; used for nothing else |

The scale (rem): 0.8125, 0.875, 1, 1.0625, 1.25, 1.5, 1.875, 2.5, 3.5.

All fonts are bundled. They are SIL OFL 1.1, self-hosted through `@fontsource`.

## Spacing, radius, elevation, layout, motion

| Token | Values |
|---|---|
| Spacing | 4px grid (`--s-1` … `--s-20`) |
| Radius | `--r-sm` 6px (small controls), `--r-md` 10px (inputs, buttons, inner cards), `--r-lg` 16px (panels), `--r-full` (chips, badges) |
| Elevation | `--e-panel` for the verification form and the result summary only; `--e-pop` for the mobile menu |
| Layout | page 72rem, report 62rem, text 40rem; gutter 16 / 24 / 32px |
| Breakpoints | 640 / 900 / 1200px |
| Motion | 120 / 200 / 420ms with one easing curve. The motions are the result entrance, the indeterminate progress bar, the menu sheet and the accordion. Everything is disabled under `prefers-reduced-motion`. |

## Components

| Component | What it does |
|---|---|
| `Button` / `LinkButton` | primary and secondary variants |
| `Badge` | tone and optional icon |
| `Card` | panel container |
| `SectionHeader` / `ReportSection` | the report's "margin" layout: heading in the start column, content in the main column; stacked on small screens |
| `StatusBanner` | icon, short title, one-line explanation; meaning is never carried by colour alone |
| `InfoCallout` | info, warning, error and quiet tones |
| `EmptyState` | what to do next |
| `MetricCard` | measured value with an optional meter |
| `Disclosure` | "تفاصيل تقنية" sections |
| `CopyButton` | copies a reference or a piece of evidence and announces "نُسخ" |
| `BrandMark` | the eight-pointed star |

Report-only pieces are in `frontend/src/result/Result.tsx`: the source card, the evidence card, the specialist panel and the AI panel.

### Added 2026-10-03: input tabs, screenshot review, text comparison, evidence map

| Piece | Where | Notes |
|---|---|---|
| Input tabs «نص» / «صورة» | `pages/Home.tsx` | ARIA tabs (`tablist`/`tab`/`tabpanel`, roving focus, ←/→/Home/End). Text is the default; the selected tab is a raised surface chip with primary text |
| Drop zone | `ocr/ImageVerify.tsx` | Dashed `--c-line-strong` frame on `--c-bg`; primary border and `--c-primary-soft` while dragging; the «اختيار صورة» button is the main control, drag-drop and paste are extras |
| File card | same | Preview (re-encoded copy, max 18rem tall), name in `<bdi>`, size, pixel dimensions (LTR), «اختيار صورة أخرى» and «إزالة الصورة» |
| OCR progress | same | Three numbered steps (check, engine, extract) with done / running / waiting states and a `<progress>` bar: a real percentage when the engine reports one, otherwise indeterminate. No timed or simulated progress |
| Review panel «راجع النص المستخرج» | same | OCR quality chip (success / info / warning badge; text "جودة استخراج النص") on `--c-surface-2`, unclear words underlined with a dotted warning rule, candidate radio cards (`--c-primary-soft` when chosen), editable quote (Naskh) and claim fields, the «الادعاء المقترح من الصورة» info badge, the full extracted text in a `Disclosure`, a quiet note that the image is not evidence, and «متابعة التحقق» |
| Text comparison «مقارنة النص» | `result/Comparison.tsx` | Two labelled rows («النص الذي أدخلته» / «النص القرآني المعتمد» or «النص المعتمد في المصدر»). Token styles: normalization-only = dotted info underline; substituted = warning tint with a thin frame + `≠`; missing from the quote = dashed warning outline + `−`; added by the user = warning tint with a dashed outline + `+`; outside the quote = muted text. Every non-identical word has a symbol and a screen-reader label, so colour never carries the meaning alone. Quran row keeps the KFGQPC font |
| Evidence & context map «خريطة الدليل والسياق» | `result/EvidenceMap.tsx` | Five stations (source, text, claim, evidence, result) as an ordered list; segments: quoted = green tint with a green base line, near context (not in the quote) = amber tint with a dashed underline, additional context = grey text; legend with swatches; evidence chips (LTR ids) jump to and focus the evidence card, which flashes once. Desktop (≥ 900px): evidence chips in a side column. Mobile: a vertical timeline with no horizontal scroll |

Motion added: the indeterminate OCR bar and the one-off evidence-card flash; both are disabled under `prefers-reduced-motion`. Muted text placed on `--c-surface-2` panels uses `--c-ink-2` so contrast stays above 4.5:1. The E2E axe check now waits for finite animations and transitions to finish before measuring contrast.

## Islamic character, kept subtle

- The eight-pointed star (two overlapping squares) is the brand mark.
- A faint star lattice sits behind the home hero only.
- The Kufi display face carries the identity.
- The Quran field has a framed, ivory treatment.

There are no mosque or crescent motifs and no gold gradients.

## Accessibility

- Skip link, landmarks and labelled navigation.
- The mobile menu is a modal dialog: focus moves into it, Tab is trapped, Escape closes it and focus returns to the menu button.
- Results are announced through `aria-live`.
- Focus is visible on every control.
- Text and statuses meet WCAG AA in both themes.
- RTL throughout, with LTR isolation for ids and Latin metadata.
- Browser E2E scans every page and state with axe in light and dark mode.
- Screenshot input: the review heading receives focus when extraction ends; extraction steps are announced through `role="status"`; validation and engine errors use `role="alert"`; candidate quotes are a native radio group with a legend.
