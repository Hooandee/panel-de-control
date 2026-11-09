import { toaster } from "@decky/api";
import { Navigation, Router } from "@decky/ui";
import { pressUpscalerKey, type UpscalerKey } from "../api";
import { translate } from "../i18n";
import { recordUiEvent } from "../system/uiEvents";
import { readRunningGame } from "../tdp/runningGame";
import { holdPage } from "./pageMemory";

interface GameWindow {
  NavigateToRunningApp?(replaceHistoryEntry: boolean): void;
  m_CompositionStateStore?: { GetCurrentlyFocusedAppidSubscribableValue?(): { Value?: unknown } | undefined };
}

export async function pressUpscalerKeyInGame(appid: string, action: UpscalerKey): Promise<{ pressed: string }> {
  let liveAppid: number | null = null;
  let stage = "focus";
  try {
    const current = readRunningGame();
    if (!current || (current.appid !== appid && String(current.liveAppid) !== appid)) throw new Error("game_changed");
    liveAppid = current.liveAppid;
    const store = (globalThis as { SteamUIStore?: { WindowStore?: { GamepadUIMainWindowInstance?: GameWindow } } }).SteamUIStore;
    const steamWindow = store?.WindowStore?.GamepadUIMainWindowInstance
      ?? Router?.WindowStore?.GamepadUIMainWindowInstance as unknown as GameWindow | undefined;
    const focus = steamWindow?.m_CompositionStateStore?.GetCurrentlyFocusedAppidSubscribableValue?.();
    if (!steamWindow?.NavigateToRunningApp || !focus || typeof focus.Value !== "number") throw new Error("game_focus_unavailable");
    holdPage();
    steamWindow.NavigateToRunningApp(false);
    Navigation.CloseSideMenus();
    const deadline = Date.now() + 2000;
    for (;;) {
      const next = readRunningGame();
      if (!next || next.appid !== current.appid || next.liveAppid !== liveAppid) throw new Error("game_changed");
      if (focus.Value === liveAppid) break;
      if (Date.now() >= deadline) throw new Error("game_focus_timeout");
      await new Promise<void>((resolve) => window.setTimeout(resolve, 50));
    }
    recordUiEvent("upscalers", "hotkey_focus", { appid: liveAppid, action, result: "ready" });
    stage = "key";
    return await pressUpscalerKey(appid, action);
  } catch (error) {
    const code = error instanceof Error && ["game_changed", "game_focus_unavailable", "game_focus_timeout"].includes(error.message)
      ? error.message : stage === "key" ? "key_failed" : "game_focus_unavailable";
    recordUiEvent("upscalers", "hotkey_error", { appid: liveAppid, action, stage, code }, false);
    try { toaster.toast({ title: "Panel de Control", body: translate("up.live.failed") }); } catch {}
    throw error;
  }
}
