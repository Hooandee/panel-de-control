import { createHash } from "node:crypto";
import {
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { basename, relative, resolve, sep } from "node:path";
import { deflateRawSync } from "node:zlib";

const ALLOWED_SUFFIXES = new Set([
  ".css", ".gif", ".jpeg", ".jpg", ".json", ".md", ".otf", ".png",
  ".svg", ".ttf", ".txt", ".webp", ".woff", ".woff2",
]);
const MAX_FILES = 2_048;
const MAX_BYTES = 64 * 1024 * 1024;
const UTF8_FLAG = 0x0800;
const ZIP_METHOD_DEFLATE = 8;
const ZIP_DATE_1980_01_01 = 0x0021;
const CSS_LOADER_STATE_FILES = new Set(["config_ROOT.json", "config_USER.json"]);

function fail(message) {
  throw new Error(message);
}

function readObject(path, label) {
  let value;
  try {
    value = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    fail(`invalid ${label}`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(`invalid ${label}`);
  return value;
}

function suffix(path) {
  const index = path.lastIndexOf(".");
  return index < 0 ? "" : path.slice(index).toLowerCase();
}

function walk(source, current = source, files = []) {
  for (const entry of readdirSync(current, { withFileTypes: true })) {
    const absolute = resolve(current, entry.name);
    const local = relative(source, absolute).split(sep).join("/");
    const display = `${basename(source)}/${local}`;
    const stat = lstatSync(absolute);
    if (stat.isSymbolicLink()) fail(`links are not permitted: ${display}`);
    if (stat.isDirectory()) {
      walk(source, absolute, files);
      continue;
    }
    if (!stat.isFile()) fail(`unsupported theme entry: ${display}`);
    if (!local.includes("/") && CSS_LOADER_STATE_FILES.has(local)) {
      fail(`CSS Loader state cannot be packaged: ${display}`);
    }
    if (!ALLOWED_SUFFIXES.has(suffix(local))) fail(`unsupported theme file: ${display}`);
    if ((stat.mode & 0o111) !== 0) fail(`executables are not permitted: ${display}`);
    files.push({ local, content: readFileSync(absolute) });
  }
  return files;
}

const CRC_TABLE = Array.from({ length: 256 }, (_, index) => {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) {
    value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
  }
  return value >>> 0;
});

function crc32(buffer) {
  let value = 0xffffffff;
  for (const byte of buffer) value = CRC_TABLE[(value ^ byte) & 0xff] ^ (value >>> 8);
  return (value ^ 0xffffffff) >>> 0;
}

function localHeader(name, content, compressed, crc) {
  const header = Buffer.alloc(30);
  header.writeUInt32LE(0x04034b50, 0);
  header.writeUInt16LE(20, 4);
  header.writeUInt16LE(UTF8_FLAG, 6);
  header.writeUInt16LE(ZIP_METHOD_DEFLATE, 8);
  header.writeUInt16LE(0, 10);
  header.writeUInt16LE(ZIP_DATE_1980_01_01, 12);
  header.writeUInt32LE(crc, 14);
  header.writeUInt32LE(compressed.length, 18);
  header.writeUInt32LE(content.length, 22);
  header.writeUInt16LE(name.length, 26);
  header.writeUInt16LE(0, 28);
  return header;
}

function centralHeader(name, content, compressed, crc, offset) {
  const header = Buffer.alloc(46);
  header.writeUInt32LE(0x02014b50, 0);
  header.writeUInt16LE(0x0314, 4);
  header.writeUInt16LE(20, 6);
  header.writeUInt16LE(UTF8_FLAG, 8);
  header.writeUInt16LE(ZIP_METHOD_DEFLATE, 10);
  header.writeUInt16LE(0, 12);
  header.writeUInt16LE(ZIP_DATE_1980_01_01, 14);
  header.writeUInt32LE(crc, 16);
  header.writeUInt32LE(compressed.length, 20);
  header.writeUInt32LE(content.length, 24);
  header.writeUInt16LE(name.length, 28);
  header.writeUInt16LE(0, 30);
  header.writeUInt16LE(0, 32);
  header.writeUInt16LE(0, 34);
  header.writeUInt16LE(0, 36);
  header.writeUInt32LE((0o100644 * 0x10000) >>> 0, 38);
  header.writeUInt32LE(offset, 42);
  return header;
}

function buildZip(rootName, files) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (const file of files) {
    const name = Buffer.from(`${rootName}/${file.local}`, "utf8");
    const compressed = deflateRawSync(file.content, { level: 9 });
    const crc = crc32(file.content);
    const local = localHeader(name, file.content, compressed, crc);
    localParts.push(local, name, compressed);
    centralParts.push(centralHeader(name, file.content, compressed, crc, offset), name);
    offset += local.length + name.length + compressed.length;
  }
  const central = Buffer.concat(centralParts);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(central.length, 12);
  end.writeUInt32LE(offset, 16);
  end.writeUInt16LE(0, 20);
  return Buffer.concat([...localParts, central, end]);
}

function main() {
  const [sourceArgument, outputArgument] = process.argv.slice(2);
  if (!sourceArgument || !outputArgument) fail("usage: package-theme.mjs <theme-directory> <output-directory>");
  const source = resolve(sourceArgument);
  const output = resolve(outputArgument);
  if (output === source || output.startsWith(`${source}${sep}`)) fail("output directory must be outside the theme source");

  const manifest = readObject(resolve(source, "theme.json"), "theme.json");
  const panel = readObject(resolve(source, "panel-theme.json"), "panel-theme.json");
  if (
    typeof manifest.name !== "string"
    || !manifest.name.trim()
    || basename(manifest.name) !== manifest.name
    || /[\\/]/.test(manifest.name)
  ) {
    fail("invalid CSS Loader theme name");
  }
  if (typeof manifest.version !== "string" || !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(manifest.version)) {
    fail("theme version must use semantic versioning without a v prefix");
  }
  if (
    panel.schemaVersion !== 1
    || typeof panel.catalogId !== "string"
    || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(panel.catalogId)
  ) {
    fail("invalid Panel theme identity");
  }

  const files = walk(source).sort((left, right) => left.local.localeCompare(right.local, "en"));
  const totalBytes = files.reduce((total, file) => total + file.content.length, 0);
  if (files.length === 0 || files.length > MAX_FILES || totalBytes > MAX_BYTES) fail("theme package exceeds safety limits");
  const archive = buildZip(manifest.name, files);
  const slug = basename(source);
  const archiveName = `${slug}.zip`;
  const descriptor = {
    schemaVersion: 1,
    id: panel.catalogId,
    cssLoaderName: manifest.name,
    version: manifest.version,
    artifact: {
      file: archiveName,
      sha256: createHash("sha256").update(archive).digest("hex"),
      size: archive.length,
    },
  };
  mkdirSync(output, { recursive: true });
  writeFileSync(resolve(output, archiveName), archive);
  writeFileSync(resolve(output, `${slug}.json`), `${JSON.stringify(descriptor, null, 2)}\n`);
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
