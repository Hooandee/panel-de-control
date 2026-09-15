export type ProtonStatus = "idle" | "scanning" | "ready" | "cleaning" | "cancelled" | "error";
export type ProtonEntryStatus = "unused" | "in_use" | "managed_by_steam" | "protected";

export interface ProtonEntry {
  id: string;
  name: string;
  tool_name: string;
  source: "steam" | "custom";
  appid: string | null;
  bytes: number | null;
  status: ProtonEntryStatus;
  selectable: boolean;
  recommended: boolean;
  reason: string | null;
}

export interface ProtonResultItem {
  id: string;
  status: "deleted" | "skipped" | "error";
  reason: string | null;
  bytes_removed: number;
}

export interface ProtonResult {
  operation_id: string;
  items: ProtonResultItem[];
  estimated_bytes_removed: number;
  cancelled: boolean;
}

export interface ProtonState {
  schema_version: 1;
  available: boolean;
  status: ProtonStatus;
  scan_id: string | null;
  coverage_complete: boolean;
  entries: ProtonEntry[];
  totals: { bytes: number; unknown: number };
  progress: { processed: number; total: number | null };
  error: string | null;
  last_result: ProtonResult | null;
}

export interface ProtonPlan {
  id: string;
  scan_id: string;
  entries: ProtonEntry[];
  estimated_bytes: number;
  expires_at: number;
}
