import { createHash } from "node:crypto";
import { lstatSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  normalizePagesBaseUrl,
  parsePublicationDescriptor,
} from "./theme-publication-contract.mjs";

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
const JSON_TYPES = new Set(["application/json"]);
const ZIP_TYPES = new Set(["application/zip"]);
const MAX_METADATA_BYTES = 64 * 1024;
const MAX_ARCHIVE_BYTES = 64 * 1024 * 1024;
const MAX_REDIRECTS = 3;

function fail(message) {
  throw new Error(message);
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function readReviewedCandidate(directory) {
  const root = resolve(directory);
  let metadata;
  let entries;
  try {
    metadata = lstatSync(root);
    entries = readdirSync(root, { withFileTypes: true });
  } catch {
    fail("reviewed theme candidate is unavailable");
  }
  if (
    metadata.isSymbolicLink()
    || !metadata.isDirectory()
    || entries.length !== 2
    || entries.some((entry) => !entry.isFile() || entry.isSymbolicLink())
    || entries.map((entry) => entry.name).sort().join("\n") !== "gallery.json\ngallery.zip"
  ) {
    fail("reviewed theme candidate is unsafe");
  }
  return {
    descriptor: readFileSync(resolve(root, "gallery.json")),
    archive: readFileSync(resolve(root, "gallery.zip")),
  };
}

function insidePagesPrefix(url, base) {
  const prefix = `${base.pathname.replace(/\/+$/, "")}/themes/v1/`;
  return url.origin === base.origin && url.pathname.startsWith(prefix);
}

async function fetchBounded(url, contentTypes, maximumBytes, base, fetchImpl) {
  let current = new URL(url);
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects += 1) {
    if (!insidePagesPrefix(current, base)) {
      fail("served theme redirect escaped the Pages prefix");
    }
    const response = await fetchImpl(current, {
      redirect: "manual",
      cache: "no-store",
      headers: {
        accept: [...contentTypes].join(", "),
        "cache-control": "no-cache",
      },
      signal: AbortSignal.timeout(15_000),
    });
    if (REDIRECT_STATUSES.has(response.status)) {
      if (redirects === MAX_REDIRECTS) fail("served theme response exceeded redirect limit");
      const location = response.headers.get("location");
      if (!location) fail("served theme redirect has no location");
      current = new URL(location, current);
      continue;
    }
    if (!response.ok) fail(`served theme response failed with HTTP ${response.status}`);
    const contentType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
    if (!contentType || !contentTypes.has(contentType)) {
      fail("served theme response has an unexpected content type");
    }
    const declaredLength = response.headers.get("content-length");
    if (declaredLength !== null) {
      const parsedLength = Number(declaredLength);
      if (!Number.isSafeInteger(parsedLength) || parsedLength < 0 || parsedLength > maximumBytes) {
        fail("served theme response exceeds its size limit");
      }
    }
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length === 0 || bytes.length > maximumBytes) {
      fail("served theme response exceeds its size limit");
    }
    return bytes;
  }
  fail("served theme response exceeded redirect limit");
}

export async function verifyPublishedTheme({
  pagesBaseUrl,
  catalogId,
  version,
  requireLatest,
  expectedDescriptorBytes,
  expectedArchiveBytes,
  fetchImpl = globalThis.fetch,
}) {
  if (typeof fetchImpl !== "function") fail("fetch is unavailable");
  if (
    !Buffer.isBuffer(expectedDescriptorBytes)
    || expectedDescriptorBytes.length === 0
    || !Buffer.isBuffer(expectedArchiveBytes)
    || expectedArchiveBytes.length === 0
  ) {
    fail("reviewed theme candidate bytes are required");
  }
  const normalizedBase = normalizePagesBaseUrl(pagesBaseUrl);
  const base = new URL(`${normalizedBase}/`);
  const immutableUrl = `${normalizedBase}/themes/v1/${catalogId}/${version}/gallery.json`;
  const immutableBytes = await fetchBounded(
    immutableUrl,
    JSON_TYPES,
    MAX_METADATA_BYTES,
    base,
    fetchImpl,
  );
  if (!immutableBytes.equals(expectedDescriptorBytes)) {
    fail("served theme descriptor differs from the reviewed candidate");
  }
  let value;
  try {
    value = JSON.parse(immutableBytes.toString("utf8"));
  } catch {
    fail("served theme descriptor is invalid");
  }
  const descriptor = parsePublicationDescriptor(value, normalizedBase);
  if (descriptor.catalogId !== catalogId || descriptor.version !== version) {
    fail("served theme descriptor does not match the requested version");
  }
  const archiveBytes = await fetchBounded(
    descriptor.artifact.url,
    ZIP_TYPES,
    MAX_ARCHIVE_BYTES,
    base,
    fetchImpl,
  );
  if (!archiveBytes.equals(expectedArchiveBytes)) {
    fail("served theme archive differs from the reviewed candidate");
  }
  if (
    archiveBytes.length !== descriptor.artifact.size
    || sha256(archiveBytes) !== descriptor.artifact.sha256
  ) {
    fail("served theme artifact does not match its descriptor");
  }
  if (requireLatest) {
    const latestUrl = new URL(`${normalizedBase}/themes/v1/${catalogId}/latest.json`);
    latestUrl.searchParams.set("verify", `${Date.now()}`);
    const latestBytes = await fetchBounded(
      latestUrl,
      JSON_TYPES,
      MAX_METADATA_BYTES,
      base,
      fetchImpl,
    );
    if (!latestBytes.equals(immutableBytes)) {
      fail("latest descriptor does not match the immutable version");
    }
  }
  return {
    catalogId,
    version,
    size: archiveBytes.length,
    sha256: descriptor.artifact.sha256,
    latest: requireLatest,
  };
}

function wait(milliseconds) {
  return new Promise((resolveWait) => setTimeout(resolveWait, milliseconds));
}

async function main() {
  const [pagesBaseUrl, catalogId, version, mode, expectedVersionDirectory] = process.argv.slice(2);
  if (
    !pagesBaseUrl
    || !catalogId
    || !version
    || !["immutable", "latest"].includes(mode)
    || !expectedVersionDirectory
  ) {
    fail("usage: verify-theme-pages.mjs <pages-base-url> <catalog-id> <version> <immutable|latest> <reviewed-version-directory>");
  }
  const expected = readReviewedCandidate(expectedVersionDirectory);
  let lastError;
  for (let attempt = 1; attempt <= 12; attempt += 1) {
    try {
      const result = await verifyPublishedTheme({
        pagesBaseUrl,
        catalogId,
        version,
        requireLatest: mode === "latest",
        expectedDescriptorBytes: expected.descriptor,
        expectedArchiveBytes: expected.archive,
      });
      process.stdout.write(`${JSON.stringify(result)}\n`);
      return;
    } catch (error) {
      lastError = error;
      if (attempt < 12) await wait(5_000);
    }
  }
  throw lastError;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
