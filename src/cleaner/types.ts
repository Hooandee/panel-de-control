export type CleanerKind = "shadercache" | "compatdata";
export type CleanerInstallation = "installed" | "not_installed" | "non_steam" | "unknown";
export type CleanerStatus = "idle" | "scanning" | "ready" | "cleaning" | "cancelled" | "error";

export interface CleanerEntry {
  id: string;
  game_id: string;
  appid: string;
  name: string | null;
  kind: CleanerKind;
  library_id: string;
  library_label: string;
  library_internal?: boolean;
  bytes: number | null;
  installation: CleanerInstallation;
  blocked_reason: string | null;
  requires_manual_selection: boolean;
  warnings: string[];
}

export interface CleanerLibrary {
  id: string;
  label: string;
  available: boolean;
  reason: string | null;
}

export interface CleanerResultItem {
  id: string;
  entry?: Pick<CleanerEntry, "appid" | "name" | "kind" | "library_label" | "library_internal">;
  status: "deleted" | "skipped" | "error";
  reason: string | null;
  bytes_removed: number;
}

export interface CleanerResult {
  operation_id: string;
  items: CleanerResultItem[];
  estimated_bytes_removed: number;
  cancelled: boolean;
}

export interface CleanerState {
  schema_version: 1;
  available: boolean;
  status: CleanerStatus;
  scan_id: string | null;
  coverage_complete: boolean;
  entries: CleanerEntry[];
  libraries: CleanerLibrary[];
  // Category totals are bytes; unknown counts entries whose size could not be read.
  totals: { shadercache: number; compatdata: number; unknown: number };
  progress: { processed: number; total: number | null };
  error: string | null;
  last_result: CleanerResult | null;
}

export interface CleanerPlan {
  id: string;
  scan_id: string;
  entries: CleanerEntry[];
  estimated_bytes: number;
  requires_prefix_confirmation: boolean;
  expires_at: number; // Unix seconds, matching the backend plan lifetime.
}
