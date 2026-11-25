import { useRef } from "react";
import { getGamePowerOwner, setGamePowerOwner, type GamePowerOwnerState, type TdpScope } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { translate } from "../i18n";
import { showModal } from "../navigation/showModal";
import { readPerformanceSettings } from "../steam/performanceSettings";
import { createPerformanceSettingsDeps } from "../steam/performanceSettingsRuntime";
import { readSteamPerformanceProfile } from "../steam/performanceRuntime";
import { runSteamPerformanceTransaction } from "../steam/performanceOwnership";
import { readRunningGame } from "./runningGame";

interface ChangeRequest {
  scope: TdpScope;
  appid: string | null;
  owner?: GamePowerOwnerState;
  isCurrent: () => boolean;
  apply: () => void;
  readbackAvailable?: boolean;
}

const showFailure = (unknown = false) => showModal(<ConfirmDialog
  title={translate("steam.performance.title")}
  desc={translate(unknown ? "steam.performance.profile.unknown" : "steam.performance.writeFailed")}
  confirmLabel={translate("steam.performance.cancel")}
  cancelLabel={translate("steam.performance.cancel")}
  onConfirm={() => {}}
/>);

export function confirmGamePowerChange({ scope, appid, owner, isCurrent, apply, readbackAvailable }: ChangeRequest): void {
  if (!isCurrent() || owner?.reset_pending) return;
  if (scope === "game" && owner && owner.context_appid !== appid) {
    showFailure(true);
    return;
  }
  if (scope === "global" || !owner || owner.supported === false || owner.explicit_owner === "pdc"
    || (owner.owner === "pdc" && owner.supported !== true)) {
    apply();
    return;
  }
  if (!appid || owner.context_appid !== appid || (owner.owner === "unresolved" || owner.steam_profile === "unknown")) {
    showFailure(true);
    return;
  }
  if (owner.owner === "steam" && readbackAvailable === false) { showFailure(true); return; }
  const game = readRunningGame();
  const current = () => {
    const live = readRunningGame();
    return isCurrent() && game?.appid === appid && live?.appid === appid && live.liveAppid === game.liveAppid;
  };
  let confirmed = false;
  const accept = () => {
      if (confirmed) return;
      confirmed = true;
      void runSteamPerformanceTransaction(async () => {
        if (!current()) throw new Error("stale_context");
        const next = await getGamePowerOwner();
        if (!current() || next.context_appid !== appid || next.revision !== owner.revision) throw new Error("stale_revision");
        const profile = readSteamPerformanceProfile(game!.liveAppid);
        if (profile === "unknown" || (owner.steam_profile === "active" && profile !== "game")
          || (owner.steam_profile === "inactive" && profile !== "global")) throw new Error("stale_profile");
        const snapshot = Object.fromEntries(readPerformanceSettings(createPerformanceSettingsDeps())
          .flatMap((control) => control.kind === "action" ? [] : [[control.id, control.value]]));
        const claimed = await setGamePowerOwner(appid, "pdc", next.revision, snapshot);
        if (!claimed.ok || !current()) throw new Error("claim_failed");
        apply();
      }).catch(() => { if (isCurrent()) showFailure(); });
  };
  if (owner.owner === "pdc") { accept(); return; }
  showModal(<ConfirmDialog
    title={translate("steam.performance.profile.game")}
    desc={translate("steam.performance.claim.desc")}
    confirmLabel={translate("steam.performance.claim")}
    cancelLabel={translate("steam.performance.cancel")}
    onConfirm={accept}
  />);
}

export function useGamePowerChangeGuard(scope: TdpScope, appid: string | null, owner?: GamePowerOwnerState, readbackAvailable?: boolean) {
  const context = useRef({ scope, appid, epoch: 0 });
  if (context.current.scope !== scope || context.current.appid !== appid) {
    context.current = { scope, appid, epoch: context.current.epoch + 1 };
  }
  return <Args extends unknown[]>(operation: (...args: Args) => void) => {
    const epoch = context.current.epoch;
    return (...args: Args) => confirmGamePowerChange({ scope, appid, owner, readbackAvailable, isCurrent: () => context.current.epoch === epoch, apply: () => operation(...args) });
  };
}
