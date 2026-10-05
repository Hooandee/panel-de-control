import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: [
      "src/**/*.{test,spec}.?(c|m)[jt]s?(x)",
      "tests/**/*.{test,spec}.?(c|m)[jt]s?(x)",
    ],
  },
});
