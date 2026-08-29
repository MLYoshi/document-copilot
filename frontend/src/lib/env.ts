// Single source of truth for environment variables.
// Components and modules must read config from here, never from import.meta.env directly.

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!apiBaseUrl) {
  throw new Error("VITE_API_BASE_URL is required but not set. See .env.example.");
}

if (URL.canParse(apiBaseUrl) === false) {
  throw new Error(`VITE_API_BASE_URL is not a valid URL: ${apiBaseUrl}`);
}

export const env = {
  apiBaseUrl,
} as const;
