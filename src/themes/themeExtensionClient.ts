export interface ThemeExtensionDescriptor {
  catalogId: string;
  cssLoaderName: string;
  version: string;
  abiVersion: 1;
  sha256: string;
}

export interface ThemeExtensionPayload extends ThemeExtensionDescriptor {
  source: string;
}

export interface ThemeExtensionRpcHost {
  list(): Promise<unknown>;
  load(catalogId: string, version: string): Promise<unknown>;
}

export interface ThemeExtensionClient {
  list(): Promise<readonly ThemeExtensionDescriptor[]>;
  load(catalogId: string, version: string): Promise<ThemeExtensionPayload>;
}

const STABLE_VERSION = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const SAFE_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SHA256 = /^[a-f0-9]{64}$/;
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;
const MAX_EXTENSION_SOURCE_BYTES = 2 * 1024 * 1024;

let configuredHost: ThemeExtensionRpcHost | undefined;
let configuredLease: symbol | null = null;

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Theme extension value must be an object");
  }
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, fields: readonly string[]): void {
  if (Object.keys(value).length !== fields.length || fields.some((field) => !(field in value))) {
    throw new Error("Theme extension fields are invalid");
  }
}

function safeCssLoaderName(value: unknown): string {
  if (
    typeof value !== "string"
    || value.length === 0
    || value.length > 128
    || value !== value.trim()
    || CONTROL_CHARACTERS.test(value)
    || value.includes("/")
    || value.includes("\\")
  ) throw new Error("Theme extension CSS Loader identity is invalid");
  return value;
}

function descriptor(value: unknown): ThemeExtensionDescriptor {
  const input = record(value);
  exact(input, ["catalogId", "cssLoaderName", "version", "abiVersion", "sha256"]);
  if (typeof input.catalogId !== "string" || !SAFE_ID.test(input.catalogId)) {
    throw new Error("Theme extension catalog identity is invalid");
  }
  if (typeof input.version !== "string" || !STABLE_VERSION.test(input.version)) {
    throw new Error("Theme extension version is invalid");
  }
  if (input.abiVersion !== 1) throw new Error("Theme extension ABI is unsupported");
  if (typeof input.sha256 !== "string" || !SHA256.test(input.sha256)) {
    throw new Error("Theme extension hash is invalid");
  }
  return {
    catalogId: input.catalogId,
    cssLoaderName: safeCssLoaderName(input.cssLoaderName),
    version: input.version,
    abiVersion: 1,
    sha256: input.sha256,
  };
}

function utf8Size(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

export function parseThemeExtensionDescriptors(value: unknown): ThemeExtensionDescriptor[] {
  if (!Array.isArray(value) || value.length > 32) {
    throw new Error("Theme extension descriptor collection is invalid");
  }
  const descriptors = value.map(descriptor);
  if (new Set(descriptors.map((item) => item.catalogId)).size !== descriptors.length) {
    throw new Error("Theme extension catalog identities are duplicated");
  }
  if (new Set(descriptors.map((item) => item.cssLoaderName)).size !== descriptors.length) {
    throw new Error("Theme extension CSS Loader identities are duplicated");
  }
  return descriptors;
}

export function parseThemeExtensionPayload(value: unknown): ThemeExtensionPayload {
  const input = record(value);
  exact(input, ["catalogId", "cssLoaderName", "version", "abiVersion", "sha256", "source"]);
  const parsedDescriptor = descriptor({
    catalogId: input.catalogId,
    cssLoaderName: input.cssLoaderName,
    version: input.version,
    abiVersion: input.abiVersion,
    sha256: input.sha256,
  });
  if (
    typeof input.source !== "string"
    || input.source.trim().length === 0
    || input.source.includes("\0")
    || utf8Size(input.source) > MAX_EXTENSION_SOURCE_BYTES
  ) throw new Error("Theme extension source is invalid");
  return { ...parsedDescriptor, source: input.source };
}

function requireHost(): ThemeExtensionRpcHost {
  if (!configuredHost || !configuredLease) throw new Error("Theme extension backend is unavailable");
  return configuredHost;
}

export function configureThemeExtensionRpcHost(host: ThemeExtensionRpcHost): () => void {
  const lease = Symbol("theme-extension-rpc-host");
  configuredHost = host;
  configuredLease = lease;
  return () => {
    if (configuredLease !== lease) return;
    configuredHost = undefined;
    configuredLease = null;
  };
}

export function createThemeExtensionClient(host?: ThemeExtensionRpcHost): ThemeExtensionClient {
  return {
    async list() {
      return parseThemeExtensionDescriptors(await (host ?? requireHost()).list());
    },
    async load(catalogId, version) {
      if (!SAFE_ID.test(catalogId) || !STABLE_VERSION.test(version)) {
        throw new Error("Theme extension request is invalid");
      }
      return parseThemeExtensionPayload(await (host ?? requireHost()).load(catalogId, version));
    },
  };
}
