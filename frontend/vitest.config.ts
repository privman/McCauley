import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    // happy-dom is leaner than jsdom and supports localStorage, which is
    // all we currently need from a DOM. Bump to jsdom if/when we test
    // anything that touches a layout or canvas API it doesn't implement.
    environment: "happy-dom",
    globals: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
