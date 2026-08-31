import { createHash } from "node:crypto";
import {
  copyFileSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
} from "node:fs";
import { basename, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

const SAFE_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SEMVER = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
const SHA256 = /^[0-9a-f]{64}$/;

function fail(message) {
  throw new Error(message);
}

function readDescriptor(path) {
  let value;
  try {
    value = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    fail("invalid bundled theme descriptor");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail("invalid bundled theme descriptor");
  }
  return value;
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function validateDescriptor(descriptor, pinDirectory) {
  const artifact = descriptor.artifact;
  if (
    descriptor.schemaVersion !== 1
    || typeof descriptor.id !== "string"
    || !SAFE_ID.test(descriptor.id)
    || typeof descriptor.cssLoaderName !== "string"
    || !descriptor.cssLoaderName.trim()
    || basename(descriptor.cssLoaderName) !== descriptor.cssLoaderName
    || /[\\/]/.test(descriptor.cssLoaderName)
    || typeof descriptor.version !== "string"
    || !SEMVER.test(descriptor.version)
    || !artifact
    || typeof artifact !== "object"
    || Array.isArray(artifact)
    || typeof artifact.file !== "string"
    || basename(artifact.file) !== artifact.file
    || !artifact.file.endsWith(".zip")
    || typeof artifact.sha256 !== "string"
    || !SHA256.test(artifact.sha256)
    || !Number.isSafeInteger(artifact.size)
    || artifact.size <= 0
  ) {
    fail("invalid bundled theme descriptor");
  }

  const archive = resolve(pinDirectory, artifact.file);
  let actualSize;
  try {
    actualSize = statSync(archive).size;
  } catch {
    fail("bundled theme archive is unavailable");
  }
  if (actualSize !== artifact.size || sha256(archive) !== artifact.sha256) {
    fail("bundled theme archive does not match its descriptor");
  }
  return archive;
}

function copyAtomically(source, destination) {
  const temporary = `${destination}.tmp-${process.pid}`;
  try {
    copyFileSync(source, temporary);
    renameSync(temporary, destination);
  } finally {
    rmSync(temporary, { force: true });
  }
}

export function readBundledThemePin(pinArgument) {
  const pinDirectory = resolve(pinArgument);
  const descriptorPath = resolve(pinDirectory, "gallery.json");
  const descriptor = readDescriptor(descriptorPath);
  const archivePath = validateDescriptor(descriptor, pinDirectory);
  return { descriptor, archivePath };
}

function main() {
  const [pinArgument, outputArgument] = process.argv.slice(2);
  if (!pinArgument || !outputArgument) {
    fail("usage: copy-bundled-theme.mjs <pin-directory> <output-directory>");
  }
  const pinDirectory = resolve(pinArgument);
  const outputDirectory = resolve(outputArgument);
  if (outputDirectory === pinDirectory || outputDirectory.startsWith(`${pinDirectory}${sep}`)) {
    fail("output directory must be outside the bundled theme pin");
  }
  const descriptorPath = resolve(pinDirectory, "gallery.json");
  const { archivePath } = readBundledThemePin(pinDirectory);

  mkdirSync(outputDirectory, { recursive: true });
  copyAtomically(archivePath, resolve(outputDirectory, basename(archivePath)));
  copyAtomically(descriptorPath, resolve(outputDirectory, "gallery.json"));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
