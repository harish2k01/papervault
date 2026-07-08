import { z } from "zod";

const ConfigSchema = z.object({
  apiBaseUrl: z.string().url(),
});

export const appConfig = ConfigSchema.parse({
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
});
