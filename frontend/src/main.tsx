import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
/* Self-hosted fonts (SIL OFL 1.1): no request to a third-party font service; works offline after setup. */
import "@fontsource/reem-kufi/500.css";
import "@fontsource/reem-kufi/600.css";
import "@fontsource/reem-kufi/700.css";
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/500.css";
import "@fontsource/ibm-plex-sans-arabic/600.css";
import "@fontsource/ibm-plex-sans-arabic/700.css";
import "@fontsource/noto-naskh-arabic/400.css";
import "@fontsource/noto-naskh-arabic/600.css";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
