import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { createRequire } from "module";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));
// Reuse the exact Rollup plugins @decky/rollup ships with, so the kiosk adds no dependencies.
const fromDecky = createRequire(createRequire(import.meta.url).resolve("@decky/rollup/package.json"));
const load = (name) => {
  const mod = fromDecky(name);
  return mod.default ?? mod;
};
const typescript = load("@rollup/plugin-typescript");
const commonjs = load("@rollup/plugin-commonjs");
const json = load("@rollup/plugin-json");
const replace = load("@rollup/plugin-replace");
const { nodeResolve } = fromDecky("@rollup/plugin-node-resolve");

const outDir = resolve(here, "../dist/kiosk");
const SHIMS = {
  "@decky/ui": resolve(here, "src/shims/deckyUi.tsx"),
  "@decky/api": resolve(here, "src/shims/deckyApi.ts"),
};

const deckyShims = {
  name: "pdc-kiosk-decky-shims",
  resolveId: (source) => SHIMS[source] ?? null,
};

const kioskAssets = {
  name: "pdc-kiosk-assets",
  writeBundle() {
    mkdirSync(outDir, { recursive: true });
    writeFileSync(resolve(outDir, "index.html"), readFileSync(resolve(here, "index.html")));
    copyFileSync(resolve(here, "assets/inter.woff2"), resolve(outDir, "inter.woff2"));
    copyFileSync(resolve(here, "assets/Inter-OFL.txt"), resolve(outDir, "Inter-OFL.txt"));
  },
};

export default {
  input: resolve(here, "src/main.tsx"),
  plugins: [
    deckyShims,
    typescript({ tsconfig: resolve(here, "tsconfig.json") }),
    json(),
    commonjs(),
    nodeResolve({ browser: true }),
    replace({ preventAssignment: true, "process.env.NODE_ENV": JSON.stringify("production") }),
    kioskAssets,
  ],
  context: "window",
  output: { file: resolve(outDir, "kiosk.js"), format: "iife", sourcemap: false },
};
