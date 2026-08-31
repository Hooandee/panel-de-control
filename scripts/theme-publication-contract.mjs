const SAFE_CATALOG_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const STABLE_SEMVER = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const SHA256 = /^[0-9a-f]{64}$/;
const NOTE_LOCALES = new Set(["es", "en", "it"]);
const MAX_NOTE_LENGTH = 1_000;
const MAX_ARTIFACT_SIZE = 64 * 1024 * 1024;

function fail(message) {
  throw new Error(message);
}

function isRecord(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function requireExactKeys(value, allowed, required, label) {
  if (!isRecord(value)) fail(`${label} must be an object`);
  const keys = Object.keys(value);
  for (const key of keys) {
    if (!allowed.has(key)) fail(`${label} contains an unknown field: ${key}`);
  }
  for (const key of required) {
    if (!Object.hasOwn(value, key)) fail(`${label} is missing: ${key}`);
  }
}

function requireStableSemver(value, label) {
  if (typeof value !== "string" || !STABLE_SEMVER.test(value)) {
    fail(`${label} must be a stable semantic version`);
  }
  return value;
}

export function normalizePagesBaseUrl(value) {
  if (typeof value !== "string" || !value) fail("Pages base URL is required");
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    fail("Pages base URL is invalid");
  }
  if (
    parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
  ) {
    fail("Pages base URL must be an HTTPS origin and path");
  }
  const pathname = parsed.pathname.replace(/\/+$/, "");
  return `${parsed.origin}${pathname}`;
}

function parseNotes(value) {
  if (value === undefined) return undefined;
  requireExactKeys(value, NOTE_LOCALES, new Set(), "release notes");
  const notes = {};
  for (const [locale, note] of Object.entries(value)) {
    if (
      typeof note !== "string"
      || note.trim().length === 0
      || [...note].length > MAX_NOTE_LENGTH
    ) {
      fail(`release note ${locale} is invalid`);
    }
    notes[locale] = note;
  }
  return notes;
}

export function parsePublicationDescriptor(value, pagesBaseUrl) {
  requireExactKeys(
    value,
    new Set([
      "schemaVersion",
      "catalogId",
      "cssLoaderName",
      "version",
      "artifact",
      "minimumVersions",
      "notes",
    ]),
    new Set([
      "schemaVersion",
      "catalogId",
      "cssLoaderName",
      "version",
      "artifact",
      "minimumVersions",
    ]),
    "publication descriptor",
  );
  if (value.schemaVersion !== 1) fail("unsupported publication schema");
  if (typeof value.catalogId !== "string" || !SAFE_CATALOG_ID.test(value.catalogId)) {
    fail("invalid publication catalog id");
  }
  if (
    typeof value.cssLoaderName !== "string"
    || value.cssLoaderName.trim().length === 0
    || value.cssLoaderName.length > 128
    || /[\\/]/.test(value.cssLoaderName)
  ) {
    fail("invalid CSS Loader theme name");
  }
  requireStableSemver(value.version, "published version");

  requireExactKeys(
    value.artifact,
    new Set(["url", "size", "sha256"]),
    new Set(["url", "size", "sha256"]),
    "publication artifact",
  );
  if (
    !Number.isSafeInteger(value.artifact.size)
    || value.artifact.size <= 0
    || value.artifact.size > MAX_ARTIFACT_SIZE
  ) {
    fail("publication artifact size is invalid");
  }
  if (typeof value.artifact.sha256 !== "string" || !SHA256.test(value.artifact.sha256)) {
    fail("publication artifact digest is invalid");
  }
  const base = normalizePagesBaseUrl(pagesBaseUrl);
  const expectedArtifactUrl = `${base}/themes/v1/${value.catalogId}/${value.version}/gallery.zip`;
  if (value.artifact.url !== expectedArtifactUrl) {
    fail("publication artifact URL is outside the registered version path");
  }

  requireExactKeys(
    value.minimumVersions,
    new Set(["panel", "cssLoader", "cssLoaderBackend"]),
    new Set(["panel", "cssLoader", "cssLoaderBackend"]),
    "minimum versions",
  );
  requireStableSemver(value.minimumVersions.panel, "minimum Panel version");
  requireStableSemver(value.minimumVersions.cssLoader, "minimum CSS Loader version");
  if (
    !Number.isSafeInteger(value.minimumVersions.cssLoaderBackend)
    || value.minimumVersions.cssLoaderBackend <= 0
  ) {
    fail("minimum CSS Loader backend is invalid");
  }
  const notes = parseNotes(value.notes);

  return {
    schemaVersion: 1,
    catalogId: value.catalogId,
    cssLoaderName: value.cssLoaderName,
    version: value.version,
    artifact: {
      url: value.artifact.url,
      size: value.artifact.size,
      sha256: value.artifact.sha256,
    },
    minimumVersions: {
      panel: value.minimumVersions.panel,
      cssLoader: value.minimumVersions.cssLoader,
      cssLoaderBackend: value.minimumVersions.cssLoaderBackend,
    },
    ...(notes === undefined ? {} : { notes }),
  };
}
