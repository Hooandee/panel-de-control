import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  rmSync,
} from "node:fs";
import { basename, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

const PAYLOAD_ENTRIES = [
  "dist",
  "main.py",
  "plugin.json",
  "package.json",
  "README.md",
  "README.en.md",
  "LICENSE",
  "py_modules",
  "assets",
  "bin",
];

function fail(message) {
  throw new Error(message);
}

function includePayloadPath(sourceRoot, sourcePath) {
  const path = relative(sourceRoot, sourcePath);
  if (lstatSync(sourcePath).isSymbolicLink()) {
    fail(`plugin payload symlink is not allowed: ${path}`);
  }
  const segments = path.split(sep);
  if (segments.includes("__pycache__")) return false;
  if (/\.(?:pyc|pyo|map)$/.test(basename(path))) return false;
  return true;
}

export function copyPluginPayload(sourceDirectory, outputDirectory) {
  const source = resolve(sourceDirectory);
  const output = resolve(outputDirectory);
  if (output === source || output.startsWith(`${source}${sep}`)) {
    fail("plugin payload output must be outside the source tree");
  }
  if (existsSync(output)) fail("plugin payload output already exists");

  mkdirSync(output, { recursive: true });
  try {
    for (const entry of PAYLOAD_ENTRIES) {
      const entrySource = resolve(source, entry);
      if (!existsSync(entrySource)) fail(`plugin payload source is missing: ${entry}`);
      cpSync(entrySource, resolve(output, entry), {
        recursive: true,
        filter: (path) => includePayloadPath(source, path),
      });
    }
  } catch (error) {
    rmSync(output, { recursive: true, force: true });
    throw error;
  }
}

function main() {
  const [sourceDirectory, outputDirectory] = process.argv.slice(2);
  if (!sourceDirectory || !outputDirectory) {
    fail("usage: copy-plugin-payload.mjs <source-directory> <output-directory>");
  }
  copyPluginPayload(sourceDirectory, outputDirectory);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
