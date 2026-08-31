export type ThemePublicationCompatibility =
  | "compatible"
  | "incompatible-panel"
  | "incompatible-css-loader";

export interface PublishedThemeRelease {
  catalogId: string;
  cssLoaderName: string;
  publishedVersion: string;
  compatibility: ThemePublicationCompatibility;
  notes: Partial<Record<"es" | "en" | "it", string>>;
}

export type ThemePublicationState =
  | { status: "unchecked" }
  | { status: "checking" }
  | { status: "disabled" }
  | { status: "published"; checkedAt: number; themes: readonly PublishedThemeRelease[] }
  | {
    status: "temporarily-unavailable" | "recoverable-failure";
    code: ThemePublicationErrorCode;
    retryable: boolean;
  };

export type ThemePublicationErrorCode =
  | "offline"
  | "tls_error"
  | "timeout"
  | "rate_limited"
  | "redirect_rejected"
  | "http_status"
  | "invalid_descriptor"
  | "descriptor_too_large"
  | "lifecycle_stopping";

const ERROR_CODES = new Set<ThemePublicationErrorCode>([
  "offline",
  "tls_error",
  "timeout",
  "rate_limited",
  "redirect_rejected",
  "http_status",
  "invalid_descriptor",
  "descriptor_too_large",
  "lifecycle_stopping",
]);
const COMPATIBILITY = new Set<ThemePublicationCompatibility>([
  "compatible",
  "incompatible-panel",
  "incompatible-css-loader",
]);
const LOCALES = new Set(["es", "en", "it"]);
const STABLE_VERSION = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const CATALOG_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Theme publication must be an object");
  }
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, fields: readonly string[]): void {
  if (Object.keys(value).length !== fields.length || fields.some((field) => !(field in value))) {
    throw new Error("Theme publication fields are invalid");
  }
}

function publicationTheme(value: unknown): PublishedThemeRelease {
  const theme = record(value);
  exact(theme, ["catalogId", "cssLoaderName", "publishedVersion", "compatibility", "notes"]);
  if (typeof theme.catalogId !== "string" || !CATALOG_ID.test(theme.catalogId)) {
    throw new Error("Published theme id is invalid");
  }
  if (
    typeof theme.cssLoaderName !== "string"
    || theme.cssLoaderName.trim().length === 0
    || theme.cssLoaderName.length > 128
  ) {
    throw new Error("Published CSS Loader name is invalid");
  }
  if (typeof theme.publishedVersion !== "string" || !STABLE_VERSION.test(theme.publishedVersion)) {
    throw new Error("Published theme version is invalid");
  }
  if (typeof theme.compatibility !== "string" || !COMPATIBILITY.has(
    theme.compatibility as ThemePublicationCompatibility,
  )) {
    throw new Error("Published theme compatibility is invalid");
  }
  const rawNotes = record(theme.notes);
  const notes: PublishedThemeRelease["notes"] = {};
  for (const [locale, note] of Object.entries(rawNotes)) {
    if (
      !LOCALES.has(locale)
      || typeof note !== "string"
      || note.trim().length === 0
      || note.length > 1_000
    ) {
      throw new Error("Published theme notes are invalid");
    }
    notes[locale as keyof PublishedThemeRelease["notes"]] = note;
  }
  return {
    catalogId: theme.catalogId,
    cssLoaderName: theme.cssLoaderName,
    publishedVersion: theme.publishedVersion,
    compatibility: theme.compatibility as ThemePublicationCompatibility,
    notes,
  };
}

export function parseThemePublication(value: unknown): Exclude<
  ThemePublicationState,
  { status: "unchecked" | "checking" }
> {
  const publication = record(value);
  if (publication.status === "disabled") {
    exact(publication, ["status"]);
    return { status: "disabled" };
  }
  if (publication.status === "published") {
    exact(publication, ["status", "checkedAt", "themes"]);
    if (
      typeof publication.checkedAt !== "number"
      || !Number.isFinite(publication.checkedAt)
      || publication.checkedAt < 0
      || !Array.isArray(publication.themes)
      || publication.themes.length > 32
    ) {
      throw new Error("Published theme collection is invalid");
    }
    const themes = publication.themes.map(publicationTheme);
    if (new Set(themes.map((theme) => theme.catalogId)).size !== themes.length) {
      throw new Error("Published theme identities are duplicated");
    }
    return { status: "published", checkedAt: publication.checkedAt, themes };
  }
  if (
    publication.status === "temporarily-unavailable"
    || publication.status === "recoverable-failure"
  ) {
    exact(publication, ["status", "code", "retryable"]);
    if (
      typeof publication.code !== "string"
      || !ERROR_CODES.has(publication.code as ThemePublicationErrorCode)
      || typeof publication.retryable !== "boolean"
    ) {
      throw new Error("Theme publication failure is invalid");
    }
    return {
      status: publication.status,
      code: publication.code as ThemePublicationErrorCode,
      retryable: publication.retryable,
    };
  }
  throw new Error("Theme publication status is invalid");
}
