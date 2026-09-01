export type CssLoaderStatus = "missing" | "disabled" | "incompatible" | "ready" | "error";
export type CssLoaderPatchType = "checkbox" | "dropdown" | "slider" | "none" | "unsupported";

export interface CssLoaderPatch {
  name: string;
  defaultValue: string;
  value: string;
  options: readonly string[];
  type: CssLoaderPatchType;
  rawType: string;
}

export interface CssLoaderTheme {
  id: string;
  name: string;
  displayName: string;
  version: string;
  author: string;
  enabled: boolean;
  patches: readonly CssLoaderPatch[];
}

export type CssLoaderErrorCode =
  | "transport"
  | "timeout"
  | "malformed_response"
  | "mutation_failed"
  | "verification_failed";

export interface CssLoaderErrorInfo {
  code: CssLoaderErrorCode;
  message: string;
}

export interface CssLoaderSnapshot {
  status: CssLoaderStatus;
  pluginVersion?: string;
  backendVersion?: number;
  requiredBackendVersion?: number;
  themes: readonly CssLoaderTheme[];
  error?: CssLoaderErrorInfo;
}
