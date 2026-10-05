import { copyFileSync, mkdirSync, writeFileSync } from "fs";
import { createRequire } from "module";
import { dirname, resolve } from "path";
import { fileURLToPath, pathToFileURL } from "url";

const here = dirname(fileURLToPath(import.meta.url));
// Reuse the exact Rollup plugins @decky/rollup ships with, so the bottom screen adds no dependencies.
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
const stringsModule = resolve(here, "../node_modules/.cache/pdc-kiosk/strings.mjs");

// The translations reach Decky's modules through src/api.ts; exporting them never calls into Decky.
const DECKY_STUBS = {
  "@decky/api": "export const callable = () => async () => { throw new Error('unavailable'); };",
  "@decky/ui": "export {};",
};

const deckyStubs = {
  name: "pdc-kiosk-decky-stubs",
  resolveId: (source) => (source in DECKY_STUBS ? `\0${source}` : null),
  load: (id) => (id.startsWith("\0") ? DECKY_STUBS[id.slice(1)] ?? null : null),
};

// The native bottom screen is Python: it reads the same translations and icons as JSON.
const nativeAssets = {
  name: "pdc-kiosk-native-assets",
  async writeBundle() {
    const { STRINGS, ICONS } = await import(`${pathToFileURL(stringsModule).href}?t=${Date.now()}`);
    mkdirSync(outDir, { recursive: true });
    writeFileSync(resolve(outDir, "strings.json"), JSON.stringify(STRINGS));
    writeFileSync(resolve(outDir, "icons.json"), JSON.stringify(ICONS));
    copyFileSync(resolve(here, "assets/inter.ttf"), resolve(outDir, "inter.ttf"));
    copyFileSync(resolve(here, "assets/Inter-OFL.txt"), resolve(outDir, "Inter-OFL.txt"));
  },
};

export default {
  input: resolve(here, "src/strings.tsx"),
  plugins: [
    deckyStubs,
    typescript({ tsconfig: resolve(here, "../tsconfig.json"), noEmitOnError: true }),
    json(),
    commonjs(),
    nodeResolve(),
    replace({ preventAssignment: true, "process.env.NODE_ENV": JSON.stringify("production") }),
    nativeAssets,
  ],
  output: { file: stringsModule, format: "es", sourcemap: false },
};
