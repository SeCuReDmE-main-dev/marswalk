import type { DataConfig } from "./types";
export function getConfig(): DataConfig {
  const mode = import.meta.env.VITE_DATA_MODE || "static";
  if (mode !== "static" && mode !== "api")
    throw new Error("VITE_DATA_MODE must be static or api.");
  return {
    mode,
    siteId: import.meta.env.VITE_SITE_ID || "jezero",
    packUrl:
      import.meta.env.VITE_PACK_URL ||
      `${import.meta.env.BASE_URL}data/jezero/v1`,
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  };
}
