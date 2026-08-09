export function desktopFanVisible(
  deviceKey: string | null | undefined,
  channel: "system" | "gpu" | undefined,
): boolean {
  return deviceKey !== "steam_machine" || channel !== "gpu";
}
