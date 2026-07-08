import { z } from "zod";

const apiBaseUrlSchema = z
  .string()
  .min(1)
  .refine((value) => value.startsWith("/") || URL.canParse(value), {
    message: "API base URL must be an absolute URL or a same-origin path",
  })
  .transform((value) => (value.length > 1 ? value.replace(/\/+$/, "") : value));

const ConfigSchema = z.object({
  apiBaseUrl: apiBaseUrlSchema,
});

export const appConfig = ConfigSchema.parse({
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api",
});
