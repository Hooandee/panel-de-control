const REASONS = new Set([
  "coverage_incomplete", "library_unavailable", "symlink", "unsafe_path", "path_changed", "mount_point",
  "runtime", "activity_unknown", "active_game", "size_unknown", "cancelled", "io_error",
  "busy", "closed", "invalid_selection", "stale_scan", "invalid_plan", "expired_plan",
  "prefix_confirmation_required", "prefix_data", "unknown_identity", "internal_error", "active_download", "partial_delete",
  "managed_by_steam", "protected_tool", "tool_in_use", "malformed_data", "media_unavailable", "media_incomplete", "media_delete_failed",
]);

export function cleanerReasonKey(reason: string | null): string {
  return `cleaner.reason.${reason && REASONS.has(reason) ? reason : "unknown"}`;
}

export function cleanerErrorCode(error: unknown): string {
  const details = [
    typeof error === "string" ? error : "",
    error instanceof Error ? error.message : "",
    ...(error && typeof error === "object"
      ? ["message", "code", "pythonTraceback"]
        .map((key) => (error as unknown as Record<string, unknown>)[key])
        .filter((value): value is string => typeof value === "string")
      : []),
  ].join(" ");
  return details.match(/[a-z_]+/g)?.find((part) => REASONS.has(part)) ?? "internal_error";
}
