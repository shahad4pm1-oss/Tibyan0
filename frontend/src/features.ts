/* Feature switches for the UI.

   IMAGE_MODE_ENABLED: the «صورة» input tab (text extraction from a screenshot in the browser, src/ocr/).
   Hidden since 2026-10-05: recognition quality on vowelled and Uthmanic-script text is not good enough to show.
   The code is kept; set this to true to bring the tab and its methodology text back (and set the same constant
   in e2e/screenshot.spec.ts so its tests run again). */
export const IMAGE_MODE_ENABLED = false;
