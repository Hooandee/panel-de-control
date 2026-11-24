import type { DesktopFanChannel, SplitFanChannel } from "../api";

export function desktopFanVisible(
  deviceKey: string | null | undefined,
  channel: "system" | "gpu" | undefined,
): boolean {
  return deviceKey !== "steam_machine" || channel !== "gpu";
}

export const isDesktopFanChannel = (
  channel: DesktopFanChannel | SplitFanChannel,
): channel is DesktopFanChannel => channel.key === "system" || "controllable" in channel;
