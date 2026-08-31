import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

import {
  normalizePagesBaseUrl,
  parsePublicationDescriptor,
} from "./theme-publication-contract.mjs";

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

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function equalFile(path, expected) {
  try {
    return readFileSync(path).equals(expected);
  } catch {
    return false;
  }
}

function retainImmutableVersion(versionRoot, descriptorBytes, archiveBytes) {
  if (!existsSync(versionRoot)) return false;
  if (
    equalFile(resolve(versionRoot, "gallery.json"), descriptorBytes)
    && equalFile(resolve(versionRoot, "gallery.zip"), archiveBytes)
  ) {
    return true;
  }
  fail("immutable theme version already exists with different bytes");
}

export async function buildThemePublication({
  sourceDirectory,
  outputDirectory,
  pagesBaseUrl,
  minimumVersions,
  notes,
}) {
  const source = resolve(sourceDirectory);
  const output = resolve(outputDirectory);
  if (output === source || output.startsWith(`${source}${sep}`)) {
    fail("publication output must be outside the theme source");
  }
  const manifest = readObject(resolve(source, "theme.json"), "theme.json");
  const panelManifest = readObject(resolve(source, "panel-theme.json"), "panel-theme.json");
  if (manifest.manifest_version !== minimumVersions?.cssLoaderBackend) {
    fail("publication backend minimum must match the CSS Loader manifest contract");
  }

  const packageDirectory = mkdtempSync(resolve(tmpdir(), "pdc-theme-publication-build-"));
  try {
    const packageResult = spawnSync(process.execPath, [
      resolve(process.cwd(), "scripts/package-theme.mjs"),
      source,
      packageDirectory,
    ], { encoding: "utf8" });
    if (packageResult.status !== 0) {
      fail(packageResult.stderr.trim() || "theme package build failed");
    }

    const slug = basename(source);
    const packageDescriptor = readObject(resolve(packageDirectory, `${slug}.json`), "package descriptor");
    const archivePath = resolve(packageDirectory, `${slug}.zip`);
    const archiveBytes = readFileSync(archivePath);
    if (
      packageDescriptor.id !== panelManifest.catalogId
      || packageDescriptor.cssLoaderName !== manifest.name
      || packageDescriptor.version !== manifest.version
      || packageDescriptor.artifact?.file !== `${slug}.zip`
      || packageDescriptor.artifact?.size !== archiveBytes.length
      || packageDescriptor.artifact?.sha256 !== sha256(archiveBytes)
    ) {
      fail("theme package output does not match its source identity");
    }

    const base = normalizePagesBaseUrl(pagesBaseUrl);
    const relativeVersionPath = `themes/v1/${panelManifest.catalogId}/${manifest.version}`;
    const descriptor = parsePublicationDescriptor({
      schemaVersion: 1,
      catalogId: panelManifest.catalogId,
      cssLoaderName: manifest.name,
      version: manifest.version,
      artifact: {
        url: `${base}/${relativeVersionPath}/gallery.zip`,
        size: archiveBytes.length,
        sha256: sha256(archiveBytes),
      },
      minimumVersions,
      ...(notes === undefined ? {} : { notes }),
    }, base);
    const descriptorBytes = Buffer.from(`${JSON.stringify(descriptor, null, 2)}\n`, "utf8");
    const catalogRoot = resolve(output, "themes/v1", descriptor.catalogId);
    const versionRoot = resolve(catalogRoot, descriptor.version);
    if (retainImmutableVersion(versionRoot, descriptorBytes, archiveBytes)) return descriptor;

    mkdirSync(catalogRoot, { recursive: true });
    const stagedVersion = mkdtempSync(resolve(catalogRoot, `.${descriptor.version}-`));
    try {
      copyFileSync(archivePath, resolve(stagedVersion, "gallery.zip"));
      writeFileSync(resolve(stagedVersion, "gallery.json"), descriptorBytes);
      if (existsSync(versionRoot)) {
        retainImmutableVersion(versionRoot, descriptorBytes, archiveBytes);
      } else {
        renameSync(stagedVersion, versionRoot);
      }
    } finally {
      rmSync(stagedVersion, { recursive: true, force: true });
    }
    return descriptor;
  } finally {
    rmSync(packageDirectory, { recursive: true, force: true });
  }
}

async function main() {
  const [sourceDirectory, outputDirectory, pagesBaseUrl, panel, cssLoader, backend, notesPath] = process.argv.slice(2);
  if (!sourceDirectory || !outputDirectory || !pagesBaseUrl || !panel || !cssLoader || !backend) {
    fail("usage: build-theme-publication.mjs <theme-directory> <output-directory> <pages-base-url> <minimum-panel> <minimum-css-loader> <minimum-css-loader-backend> [notes.json]");
  }
  const notes = notesPath === undefined ? undefined : readObject(resolve(notesPath), "release notes");
  const descriptor = await buildThemePublication({
    sourceDirectory,
    outputDirectory,
    pagesBaseUrl,
    minimumVersions: {
      panel,
      cssLoader,
      cssLoaderBackend: Number(backend),
    },
    notes,
  });
  process.stdout.write(`${JSON.stringify(descriptor)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
