import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  readFileSync,
  renameSync,
  rmSync,
} from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { parsePublicationDescriptor } from "./theme-publication-contract.mjs";

const SAFE_CATALOG_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const STABLE_SEMVER = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;

function fail(message) {
  throw new Error(message);
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function compareVersions(left, right) {
  const leftParts = left.split(".").map(BigInt);
  const rightParts = right.split(".").map(BigInt);
  for (let index = 0; index < 3; index += 1) {
    if (leftParts[index] < rightParts[index]) return -1;
    if (leftParts[index] > rightParts[index]) return 1;
  }
  return 0;
}

function readDescriptor(path, pagesBaseUrl, label) {
  let value;
  try {
    value = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    fail(`${label} descriptor is invalid`);
  }
  return parsePublicationDescriptor(value, pagesBaseUrl);
}

function verifyVersionArchive(versionRoot, descriptor) {
  const archivePath = resolve(versionRoot, "gallery.zip");
  let archiveBytes;
  try {
    archiveBytes = readFileSync(archivePath);
  } catch {
    fail("staged theme artifact is unavailable");
  }
  if (
    archiveBytes.length !== descriptor.artifact.size
    || sha256(archiveBytes) !== descriptor.artifact.sha256
  ) {
    fail("staged theme artifact does not match its descriptor");
  }
  return archivePath;
}

function readThemeManifest(archivePath, cssLoaderName) {
  const result = spawnSync(
    "unzip",
    ["-p", archivePath, `${cssLoaderName}/theme.json`],
    { encoding: "utf8" },
  );
  if (result.status !== 0) fail("staged theme manifest is unavailable");
  let manifest;
  try {
    manifest = JSON.parse(result.stdout);
  } catch {
    fail("staged theme manifest is invalid");
  }
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    fail("staged theme manifest is invalid");
  }
  return manifest;
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireBackwardCompatiblePatches(previousManifest, candidateManifest) {
  if (!isRecord(previousManifest.patches) || !isRecord(candidateManifest.patches)) {
    fail("published patch contract is not backward compatible");
  }
  for (const [patchName, previousPatch] of Object.entries(previousManifest.patches)) {
    const candidatePatch = candidateManifest.patches[patchName];
    if (
      !isRecord(previousPatch)
      || !isRecord(candidatePatch)
      || typeof previousPatch.type !== "string"
      || candidatePatch.type !== previousPatch.type
      || !isRecord(previousPatch.values)
      || !isRecord(candidatePatch.values)
      || Object.keys(previousPatch.values).some((value) => !Object.hasOwn(candidatePatch.values, value))
    ) {
      fail("published patch contract is not backward compatible");
    }
  }
}

export async function promoteStagedCandidate({
  pagesDirectory,
  pagesBaseUrl,
  catalogId,
  version,
}) {
  if (!SAFE_CATALOG_ID.test(catalogId) || !STABLE_SEMVER.test(version)) {
    fail("promotion identity is invalid");
  }
  const pagesRoot = resolve(pagesDirectory);
  const catalogRoot = resolve(pagesRoot, "themes/v1", catalogId);
  const versionRoot = resolve(catalogRoot, version);
  const immutableDescriptorPath = resolve(versionRoot, "gallery.json");
  if (!existsSync(immutableDescriptorPath)) fail("staged theme version is unavailable");
  const immutableDescriptorBytes = readFileSync(immutableDescriptorPath);
  const candidate = readDescriptor(immutableDescriptorPath, pagesBaseUrl, "staged theme");
  if (candidate.catalogId !== catalogId || candidate.version !== version) {
    fail("staged theme identity does not match the promotion request");
  }
  const candidateArchive = verifyVersionArchive(versionRoot, candidate);
  const latestPath = resolve(catalogRoot, "latest.json");
  let previousVersion = null;

  if (existsSync(latestPath)) {
    const latestBytes = readFileSync(latestPath);
    const latest = readDescriptor(latestPath, pagesBaseUrl, "latest theme");
    previousVersion = latest.version;
    if (latest.catalogId !== catalogId || latest.cssLoaderName !== candidate.cssLoaderName) {
      fail("latest theme identity does not match the staged candidate");
    }
    const latestImmutablePath = resolve(catalogRoot, latest.version, "gallery.json");
    if (!existsSync(latestImmutablePath) || !readFileSync(latestImmutablePath).equals(latestBytes)) {
      fail("latest descriptor is not an exact immutable publication");
    }
    const latestArchive = verifyVersionArchive(resolve(catalogRoot, latest.version), latest);
    const comparison = compareVersions(candidate.version, latest.version);
    if (comparison === 0) {
      if (!immutableDescriptorBytes.equals(latestBytes)) {
        fail("latest descriptor differs from the immutable version");
      }
      return {
        status: "unchanged",
        catalogId,
        version,
        previousVersion,
      };
    }
    if (comparison < 0) fail("promotion version must be newer than latest");
    requireBackwardCompatiblePatches(
      readThemeManifest(latestArchive, latest.cssLoaderName),
      readThemeManifest(candidateArchive, candidate.cssLoaderName),
    );
  }

  const temporary = `${latestPath}.tmp-${process.pid}`;
  try {
    copyFileSync(immutableDescriptorPath, temporary);
    renameSync(temporary, latestPath);
  } finally {
    rmSync(temporary, { force: true });
  }
  return {
    status: "promoted",
    catalogId,
    version,
    previousVersion,
  };
}

async function main() {
  const [pagesDirectory, pagesBaseUrl, catalogId, version] = process.argv.slice(2);
  if (!pagesDirectory || !pagesBaseUrl || !catalogId || !version) {
    fail("usage: promote-theme-pages.mjs <pages-directory> <pages-base-url> <catalog-id> <version>");
  }
  const result = await promoteStagedCandidate({
    pagesDirectory,
    pagesBaseUrl,
    catalogId,
    version,
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
