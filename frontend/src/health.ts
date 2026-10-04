import { createContext, useContext, useEffect, useState } from "react";
import { getJson } from "./api";

export type Health = {
  status: string;
  llm_mode: "REAL_LLM" | "LLM_UNAVAILABLE" | "TEST_DOUBLE_NON_PRODUCTION";
  search_mode: string | null;
  app_version?: string;
  components: {
    quran_corpus?: { passages: number; status: string };
    hadith_corpus?: { passages: number; status: string; by_collection?: Record<string, number> };
    llm?: { configured: boolean; provider: string | null; model: string | null; mode: string };
  };
};

/** undefined = loading, null = backend unreachable */
export const HealthContext = createContext<Health | null | undefined>(undefined);
export const useHealth = () => useContext(HealthContext);

export function useHealthLoader() {
  const [h, setH] = useState<Health | null | undefined>(undefined);
  useEffect(() => { getJson<Health>("/health").then(setH); }, []);
  return h;
}
