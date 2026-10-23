import { createRequire } from "module";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));
const fromDecky = createRequire(createRequire(import.meta.url).resolve("@decky/rollup/package.json"));
const load = (name) => {
  const mod = fromDecky(name);
  return mod.default ?? mod;
};
const typescript = load("@rollup/plugin-typescript");
const { nodeResolve } = fromDecky("@rollup/plugin-node-resolve");

export default {
  input: resolve(here, "../../src/windowsThemeHost/entry.ts"),
  plugins: [
    typescript({ tsconfig: resolve(here, "../../tsconfig.json"), noEmitOnError: true }),
    nodeResolve(),
  ],
  output: {
    file: resolve(here, "../../dist/windows/steam-theme-host.js"),
    format: "iife",
    sourcemap: false,
  },
};
