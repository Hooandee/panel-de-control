import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
} from "node:fs";
import { basename, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

import { parsePublicationDescriptor } from "./theme-publication-contract.mjs";

const MAX_PAGES_BYTES = 900 * 1024 * 1024;

function fail(message) {
  throw new Error(message);
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function readCandidate(candidateDirectory, pagesBaseUrl) {
  const metadata = lstatSync(candidateDirectory);
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    fail("candidate version directory is unsafe");
  }
  const entries = readdirSync(candidateDirectory, { withFileTypes: true });
  if (
    entries.length !== 2
    || entries.some((entry) => !entry.isFile() || entry.isSymbolicLink())
    || entries.map((entry) => entry.name).sort().join("\n") !== "gallery.json\ngallery.zip"
  ) {
    fail("candidate version contains unexpected files");
  }
  let value;
  try {
    value = JSON.parse(readFileSync(resolve(candidateDirectory, "gallery.json"), "utf8"));
  } catch {
    fail("candidate descriptor is invalid");
  }
  const descriptor = parsePublicationDescriptor(value, pagesBaseUrl);
  if (basename(candidateDirectory) !== descriptor.version) {
    fail("candidate directory does not match its published version");
  }
  const descriptorBytes = readFileSync(resolve(candidateDirectory, "gallery.json"));
  const archiveBytes = readFileSync(resolve(candidateDirectory, "gallery.zip"));
  if (
    archiveBytes.length !== descriptor.artifact.size
    || sha256(archiveBytes) !== descriptor.artifact.sha256
  ) {
    fail("candidate archive does not match its descriptor");
  }
  return { descriptor, descriptorBytes, archiveBytes };
}

function treeSize(path, topLevel = true) {
  if (!existsSync(path)) return 0;
  const metadata = lstatSync(path);
  if (metadata.isSymbolicLink()) fail("Pages tree contains a symbolic link");
  if (metadata.isFile()) return metadata.size;
  if (!metadata.isDirectory()) fail("Pages tree contains an unsupported entry");
  let total = 0;
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    if (topLevel && entry.name === ".git") continue;
    total += treeSize(resolve(path, entry.name), false);
    if (total >= MAX_PAGES_BYTES) return total;
  }
  return total;
}

function sameVersion(destination, descriptorBytes, archiveBytes) {
  if (!existsSync(destination)) return false;
  const metadata = lstatSync(destination);
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    fail("immutable version destination is unsafe");
  }
  try {
    return readFileSync(resolve(destination, "gallery.json")).equals(descriptorBytes)
      && readFileSync(resolve(destination, "gallery.zip")).equals(archiveBytes)
      && readdirSync(destination).sort().join("\n") === "gallery.json\ngallery.zip";
  } catch {
    return false;
  }
}

export async function stageImmutableCandidate({
  candidateVersionDirectory,
  pagesDirectory,
  pagesBaseUrl,
}) {
  const candidateDirectory = resolve(candidateVersionDirectory);
  const pagesRoot = resolve(pagesDirectory);
  if (pagesRoot === candidateDirectory || pagesRoot.startsWith(`${candidateDirectory}${sep}`)) {
    fail("Pages directory must be outside the candidate version");
  }
  const { descriptor, descriptorBytes, archiveBytes } = readCandidate(
    candidateDirectory,
    pagesBaseUrl,
  );
  const existingBytes = treeSize(pagesRoot);
  if (existingBytes >= MAX_PAGES_BYTES) fail("Pages tree must remain below 900 MiB");

  const catalogRoot = resolve(pagesRoot, "themes/v1", descriptor.catalogId);
  const destination = resolve(catalogRoot, descriptor.version);
  if (existsSync(destination)) {
    if (!sameVersion(destination, descriptorBytes, archiveBytes)) {
      fail("immutable version already exists with different bytes");
    }
    return {
      status: "unchanged",
      catalogId: descriptor.catalogId,
      version: descriptor.version,
    };
  }
  if (existingBytes + descriptorBytes.length + archiveBytes.length >= MAX_PAGES_BYTES) {
    fail("Pages tree must remain below 900 MiB");
  }

  mkdirSync(catalogRoot, { recursive: true });
  const staged = mkdtempSync(resolve(catalogRoot, `.${descriptor.version}-`));
  try {
    copyFileSync(resolve(candidateDirectory, "gallery.json"), resolve(staged, "gallery.json"));
    copyFileSync(resolve(candidateDirectory, "gallery.zip"), resolve(staged, "gallery.zip"));
    if (existsSync(destination)) {
      if (!sameVersion(destination, descriptorBytes, archiveBytes)) {
        fail("immutable version already exists with different bytes");
      }
    } else {
      renameSync(staged, destination);
    }
  } finally {
    rmSync(staged, { recursive: true, force: true });
  }
  return {
    status: "staged",
    catalogId: descriptor.catalogId,
    version: descriptor.version,
  };
}

async function main() {
  const [candidateVersionDirectory, pagesDirectory, pagesBaseUrl] = process.argv.slice(2);
  if (!candidateVersionDirectory || !pagesDirectory || !pagesBaseUrl) {
    fail("usage: stage-theme-pages.mjs <candidate-version-directory> <pages-directory> <pages-base-url>");
  }
  const result = await stageImmutableCandidate({
    candidateVersionDirectory,
    pagesDirectory,
    pagesBaseUrl,
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
