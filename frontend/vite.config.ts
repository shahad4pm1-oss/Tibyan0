/// <reference types="node" />
import { createReadStream, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/* Screenshot verification runs OCR in the visitor's browser (tesseract.js). Its worker, WebAssembly core and the
   Arabic model are served from this site under /ocr/ - never from a CDN - straight out of node_modules, so the
   versions are the ones pinned in package-lock.json. Dev: served by a middleware. Build: emitted into dist/ocr/. */
const require = createRequire(import.meta.url);
const OCR_ASSETS: Record<string, string> = {
  "ocr/worker.min.js": require.resolve("tesseract.js/dist/worker.min.js"),
  // OEM 1 (LSTM only): the worker picks one of these by WebAssembly feature detection
  "ocr/core/tesseract-core-relaxedsimd-lstm.wasm.js": require.resolve("tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm.js"),
  "ocr/core/tesseract-core-simd-lstm.wasm.js": require.resolve("tesseract.js-core/tesseract-core-simd-lstm.wasm.js"),
  "ocr/core/tesseract-core-lstm.wasm.js": require.resolve("tesseract.js-core/tesseract-core-lstm.wasm.js"),
  // tessdata_best (integer) Arabic LSTM model, gzip-compressed; the worker decompresses it itself
  "ocr/lang/ara.traineddata.gz": require.resolve("@tesseract.js-data/ara/4.0.0_best_int/ara.traineddata.gz"),
};

function ocrAssets(): Plugin {
  return {
    name: "tibyan-ocr-assets",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const file = OCR_ASSETS[(req.url ?? "").split("?")[0].replace(/^\//, "")];
        if (!file || (req.method !== "GET" && req.method !== "HEAD")) return next();
        res.setHeader("Content-Type", file.endsWith(".gz") ? "application/octet-stream" : "text/javascript; charset=utf-8");
        res.setHeader("Content-Length", String(statSync(file).size));
        res.setHeader("X-Content-Type-Options", "nosniff");
        if (req.method === "HEAD") return res.end();
        createReadStream(file).pipe(res);
      });
    },
    generateBundle() {
      for (const [fileName, file] of Object.entries(OCR_ASSETS)) {
        this.emitFile({ type: "asset", fileName, source: readFileSync(file) });
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), ocrAssets()],
});
