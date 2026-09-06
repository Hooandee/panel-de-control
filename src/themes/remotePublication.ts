import type { Lang } from "../i18n";

export type ThemePublicationCompatibility =
  | "compatible"
  | "incompatible-panel"
  | "incompatible-css-loader";

export type PublishedLocalizedText = Readonly<Record<Lang, string>>;
export type PublishedNotes = PublishedLocalizedText | Readonly<{
  es?: never;
  en?: never;
  it?: never;
}>;

export interface PublishedThemeRelease {
  catalogId: string;
  cssLoaderName: string;
  publishedVersion: string;
  displayName: PublishedLocalizedText;
  description: PublishedLocalizedText;
  author: string;
  tags: readonly string[];
  notes: PublishedNotes;
  compatibility: ThemePublicationCompatibility;
  exclusiveGroup?: string;
}

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

export type ThemePublicationState =
  | { status: "unchecked" }
  | { status: "checking" }
  | { status: "disabled" }
  | { status: "published"; checkedAt: number; themes: readonly PublishedThemeRelease[] }
  | {
    status: "cached";
    checkedAt: number;
    themes: readonly PublishedThemeRelease[];
    code: ThemePublicationErrorCode;
    retryable: boolean;
  }
  | {
    status: "temporarily-unavailable" | "recoverable-failure";
    code: ThemePublicationErrorCode;
    retryable: boolean;
  };

const ERROR_CODES = new Set<ThemePublicationErrorCode>([
  "offline", "tls_error", "timeout", "rate_limited", "redirect_rejected",
  "http_status", "invalid_descriptor", "descriptor_too_large", "lifecycle_stopping",
]);
const COMPATIBILITY = new Set<ThemePublicationCompatibility>([
  "compatible", "incompatible-panel", "incompatible-css-loader",
]);
const LOCALES = ["es", "en", "it"] as const;
const STABLE_VERSION = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const SAFE_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

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

function safeText(value: unknown, maximum: number, label: string): string {
  if (
    typeof value !== "string"
    || value.trim().length === 0
    || [...value].length > maximum
  ) throw new Error(`${label} is invalid`);
  return value;
}

function localizedText(value: unknown, maximum: number, label: string): PublishedLocalizedText {
  const input = record(value);
  exact(input, LOCALES);
  return {
    es: safeText(input.es, maximum, label),
    en: safeText(input.en, maximum, label),
    it: safeText(input.it, maximum, label),
  };
}

function publishedNotes(value: unknown): PublishedNotes {
  const input = record(value);
  if (Object.keys(input).length === 0) return {};
  return localizedText(input, 1_000, "Published notes");
}

function publicationTheme(value: unknown): PublishedThemeRelease {
  const theme = record(value);
  const required = [
    "catalogId", "cssLoaderName", "publishedVersion", "displayName", "description",
    "author", "tags", "notes", "compatibility",
  ];
  const allowed = theme.exclusiveGroup === undefined ? required : [...required, "exclusiveGroup"];
  exact(theme, allowed);
  if (typeof theme.catalogId !== "string" || !SAFE_ID.test(theme.catalogId)) {
    throw new Error("Published theme id is invalid");
  }
  const cssLoaderName = safeText(theme.cssLoaderName, 128, "Published CSS Loader name");
  if (cssLoaderName.includes("/") || cssLoaderName.includes("\\")) {
    throw new Error("Published CSS Loader name is invalid");
  }
  if (typeof theme.publishedVersion !== "string" || !STABLE_VERSION.test(theme.publishedVersion)) {
    throw new Error("Published theme version is invalid");
  }
  if (typeof theme.compatibility !== "string" || !COMPATIBILITY.has(
    theme.compatibility as ThemePublicationCompatibility,
  )) throw new Error("Published theme compatibility is invalid");
  if (!Array.isArray(theme.tags) || theme.tags.length > 8) {
    throw new Error("Published theme tags are invalid");
  }
  const tags = theme.tags.map((tag) => {
    if (typeof tag !== "string" || !SAFE_ID.test(tag)) {
      throw new Error("Published theme tag is invalid");
    }
    return tag;
  });
  if (
    theme.exclusiveGroup !== undefined
    && (typeof theme.exclusiveGroup !== "string" || !SAFE_ID.test(theme.exclusiveGroup))
  ) throw new Error("Published exclusive group is invalid");
  return {
    catalogId: theme.catalogId,
    cssLoaderName,
    publishedVersion: theme.publishedVersion,
    displayName: localizedText(theme.displayName, 80, "Published display name"),
    description: localizedText(theme.description, 400, "Published description"),
    author: safeText(theme.author, 80, "Published author"),
    tags,
    notes: publishedNotes(theme.notes),
    compatibility: theme.compatibility as ThemePublicationCompatibility,
    ...(theme.exclusiveGroup === undefined ? {} : { exclusiveGroup: theme.exclusiveGroup }),
  };
}

function publicationThemes(value: unknown): PublishedThemeRelease[] {
  if (!Array.isArray(value) || value.length > 32) {
    throw new Error("Published theme collection is invalid");
  }
  const themes = value.map(publicationTheme);
  if (new Set(themes.map((theme) => theme.catalogId)).size !== themes.length) {
    throw new Error("Published theme identities are duplicated");
  }
  if (new Set(themes.map((theme) => theme.cssLoaderName)).size !== themes.length) {
    throw new Error("Published CSS Loader identities are duplicated");
  }
  return themes;
}

function checkedAt(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error("Published catalog timestamp is invalid");
  }
  return value;
}

function failureCode(value: unknown): ThemePublicationErrorCode {
  if (typeof value !== "string" || !ERROR_CODES.has(value as ThemePublicationErrorCode)) {
    throw new Error("Theme publication failure is invalid");
  }
  return value as ThemePublicationErrorCode;
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
    return {
      status: "published",
      checkedAt: checkedAt(publication.checkedAt),
      themes: publicationThemes(publication.themes),
    };
  }
  if (publication.status === "cached") {
    exact(publication, ["status", "checkedAt", "themes", "code", "retryable"]);
    if (typeof publication.retryable !== "boolean") throw new Error("Theme cache retry is invalid");
    return {
      status: "cached",
      checkedAt: checkedAt(publication.checkedAt),
      themes: publicationThemes(publication.themes),
      code: failureCode(publication.code),
      retryable: publication.retryable,
    };
  }
  if (
    publication.status === "temporarily-unavailable"
    || publication.status === "recoverable-failure"
  ) {
    exact(publication, ["status", "code", "retryable"]);
    if (typeof publication.retryable !== "boolean") throw new Error("Theme retry state is invalid");
    return {
      status: publication.status,
      code: failureCode(publication.code),
      retryable: publication.retryable,
    };
  }
  throw new Error("Theme publication status is invalid");
}

export function localizePublishedText(
  text: Readonly<Partial<Record<Lang, string>>>,
  locale: Lang,
): string {
  return [text[locale], text.en, text.es, text.it]
    .find((value): value is string => typeof value === "string" && value.trim().length > 0) ?? "";
}
