import { useEffect, useRef, useState, type FC } from "react";
import { DialogButton } from "@decky/ui";
import { LuMonitorCog } from "react-icons/lu";
import { getGamePowerOwner, setGamePowerOwner, updateGameSteamSetting, type GamePowerOwnerState } from "../api";
import { useI18n } from "../i18n";
import { showModal } from "../navigation/showModal";
import { readPerformanceSettings, writePerformanceSetting, type PerformanceSettingControl } from "../steam/performanceSettings";
import { createPerformanceSettingsDeps } from "../steam/performanceSettingsRuntime";
import { readSteamPerformanceProfile, subscribeSteamPerformanceState } from "../steam/performanceRuntime";
import { recordSteamPerformanceDiagnostic } from "../steam/performanceDiagnostics";
import { subscribePowerOwnershipChanged } from "../tdp/powerOwnershipInvalidation";
import { readRunningGame } from "../tdp/runningGame";
import { reapplySteamPowerSettings, runSteamPerformanceTransaction } from "../steam/performanceOwnership";
import { resetManagedGamePerformance } from "../steam/performanceReset";
import { theme } from "../theme";
import { Collapsible } from "./Collapsible";
import { ConfirmDialog } from "./ConfirmDialog";
import { SteamPerformanceControls } from "./SteamPerformanceControls";

const deps = createPerformanceSettingsDeps();
const valuesOf = (controls: PerformanceSettingControl[]) => Object.fromEntries(
  controls.flatMap((control) => control.kind === "action" ? [] : [[control.id, control.value]]),
);

type PendingSelection = { failed?: boolean; id: PerformanceSettingControl["id"]; value: number | boolean; deadline: number | null; stableAppid: string | null; runningGameId: number | null; scope: "global" | "game" };
// Steam remounts QAM while a context menu is open; the selection belongs to the profile, not that mount.
const pendingSelections = new Map<string, PendingSelection>();

export const SteamPerformanceCard: FC<{
  profileScope?: "global" | "game";
  runningGameId?: number | null;
}> = ({ profileScope = "global", runningGameId = null }) => {
  const { t } = useI18n();
  const liveGame = readRunningGame();
  const stableAppid = liveGame?.liveAppid === runningGameId ? liveGame.appid : null;
  const activeContext = useRef({ profileScope, runningGameId });
  activeContext.current = { profileScope, runningGameId };
  const mutation = useRef(false);
  const selectionKey = JSON.stringify([stableAppid, runningGameId, profileScope]);
  const pending = {
    get current(): PendingSelection | null { return pendingSelections.get(selectionKey) ?? null; },
    set current(value: PendingSelection | null) {
      if (value) pendingSelections.set(selectionKey, value);
      else pendingSelections.delete(selectionKey);
    },
  };
  const refreshControls = () => {
    const observed = readPerformanceSettings(deps);
    const intent = pending.current;
    if (!intent) { setControls(observed); return; }
    if ((readRunningGame()?.appid ?? null) !== intent.stableAppid
      || deps.runningGameId() !== intent.runningGameId
      || readSteamPerformanceProfile(intent.runningGameId) !== intent.scope) {
      pending.current = null;
      setControls(observed);
      return;
    }
    if (intent.failed) {
      pending.current = null;
      setFailed(true);
      setControls(observed);
      return;
    }
    const control = observed.find((item) => item.id === intent.id);
    if (intent.deadline !== null && control && control.kind !== "action" && control.value === intent.value) {
      pending.current = null;
      setControls(observed);
    } else if (intent.deadline !== null && Date.now() >= intent.deadline) {
      pending.current = null;
      setFailed(true);
      setControls(observed);
      recordSteamPerformanceDiagnostic("control", { status: "readback_timeout", control_id: intent.id });
    } else {
      setControls(observed.map((item) => {
        if (item.id !== intent.id) return item;
        if (item.kind === "toggle" && typeof intent.value === "boolean") return { ...item, value: intent.value };
        if ((item.kind === "options" || item.kind === "slider") && typeof intent.value === "number") return { ...item, value: intent.value };
        return item;
      }));
    }
  };
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [controls, setControls] = useState<PerformanceSettingControl[]>([]);
  const [owner, setOwner] = useState<GamePowerOwnerState | null>(null);
  const [profile, setProfile] = useState(() => readSteamPerformanceProfile(runningGameId));
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    let latest = 0;
    const refresh = () => {
      if (!alive) return;
      refreshControls();
      setProfile(readSteamPerformanceProfile(runningGameId));
      const request = ++latest;
      void getGamePowerOwner().then((next) => { if (alive && request === latest && !mutation.current) setOwner(next); }).catch(() => { if (alive && request === latest && !mutation.current) setOwner(null); });
    };
    setOwner(null);
    refresh();
    const unsubscribe = subscribeSteamPerformanceState(refresh);
    const unsubscribeOwnership = subscribePowerOwnershipChanged(refresh);
    const timer = setInterval(refresh, 2000);
    const pendingTimer = setInterval(() => { if (pending.current) refreshControls(); }, 100);
    return () => { alive = false; clearInterval(timer); clearInterval(pendingTimer); unsubscribe(); unsubscribeOwnership(); };
  }, [runningGameId, profileScope]);
  const context = { scope: profileScope, runningGameId };
  const game = profileScope === "game" && runningGameId !== null;
  const currentOwner = owner?.context_appid === stableAppid ? owner : null;
  const matching = profile === profileScope;
  const readable = (matching || profile === "unknown") && controls.some((control) => control.kind !== "action");
  const ready = matching && readable;
  const managedGame = game && currentOwner?.supported === true;
  const ownershipLost = currentOwner?.reason === "ownership_capability_lost";
  const ownershipPending = ownershipLost || game && (!currentOwner || currentOwner.supported === undefined || currentOwner.reset_pending === true);
  const own = managedGame && currentOwner?.explicit_owner === "pdc";
  const execute = (id: PerformanceSettingControl["id"], value: number | boolean | undefined, expected?: GamePowerOwnerState) => runSteamPerformanceTransaction(async () => {
    if (mutation.current) return;
    const validContext = () => activeContext.current.runningGameId === runningGameId
      && activeContext.current.profileScope === profileScope
      && (readRunningGame()?.appid ?? null) === stableAppid
      && deps.runningGameId() === runningGameId
      && readSteamPerformanceProfile(runningGameId) === profileScope;
    if (!validContext()) return;
    mutation.current = true;
    setBusy(true);
    setFailed(false);
    if (value !== undefined) {
      pending.current = { id, value, deadline: null, stableAppid, runningGameId, scope: profileScope };
      refreshControls();
    }
    try {
      if (deps.runningGameId() !== runningGameId || readSteamPerformanceProfile(runningGameId) !== profileScope) throw new Error("stale_context");
      if (id === "reset") {
        const state = await getGamePowerOwner();
        if (!validContext() || state.context_appid !== stableAppid) throw new Error("stale_context");
        if (state.reason === "ownership_capability_lost") throw new Error("ownership_capability_lost");
        if (state.supported === true && (game || runningGameId === null)) {
          setOwner(await resetManagedGamePerformance(deps, context, state, validContext));
          recordSteamPerformanceDiagnostic("control", { status: "reset_confirmed", control_id: id });
          return;
        }
      }
      if (managedGame) {
        let state = await getGamePowerOwner();
        if (!validContext() || state.context_appid !== stableAppid) throw new Error("stale_context");
        if (state.reason === "ownership_capability_lost") throw new Error("ownership_capability_lost");
        if (expected && state.revision !== expected.revision) throw new Error("stale_revision");
        if (state.explicit_owner !== "pdc") {
          const claimed = await setGamePowerOwner(stableAppid!, "pdc", state.revision, valuesOf(readPerformanceSettings(deps)));
          if (!claimed.ok) throw new Error(claimed.detail ?? "claim_failed");
          state = claimed;
          if (!validContext()) throw new Error("stale_context");
        }
        if (value === undefined) throw new Error("reset_requires_snapshot");
        const saved = await updateGameSteamSetting(stableAppid!, state.revision, id, value);
        if (!saved.ok) throw new Error(saved.detail ?? "save_failed");
        if (!validContext()) throw new Error("stale_context");
        setOwner(saved);
      }
      if (!validContext()) throw new Error("stale_context");
      const result = await writePerformanceSetting(deps, context, id, value);
      if (result.status !== "request_sent" && result.status !== "unchanged") throw new Error(result.status);
      if (pending.current?.id === id) pending.current.deadline = Date.now() + 4000;
      recordSteamPerformanceDiagnostic("control", { status: result.status, control_id: id });
    } catch {
      if (pending.current) pending.current.failed = true;
      if (mounted.current) setFailed(true);
      recordSteamPerformanceDiagnostic("control", { status: "write_failed", control_id: id });
    } finally { mutation.current = false; if (mounted.current) { setBusy(false); refreshControls(); } }
  });
  const change = (id: PerformanceSettingControl["id"], value?: number | boolean) => {
    if (!ready || busy || ownershipPending) return;
    if (managedGame && !own && id !== "reset") {
      let confirmed = false;
      showModal(<ConfirmDialog title={t("steam.performance.profile.game")} desc={t("steam.performance.claim.desc")}
        confirmLabel={t("steam.performance.claim")} cancelLabel={t("steam.performance.cancel")}
        onConfirm={() => { if (confirmed) return; confirmed = true; void execute(id, value, currentOwner!); }} />);
    } else { void execute(id, value); }
  };
  const release = () => runSteamPerformanceTransaction(async () => {
    if (!currentOwner || !own || mutation.current || !mounted.current
      || activeContext.current.runningGameId !== runningGameId
      || activeContext.current.profileScope !== profileScope
      || deps.runningGameId() !== runningGameId) return;
    mutation.current = true;
    setBusy(true);
    try {
      const result = await setGamePowerOwner(stableAppid!, "steam", currentOwner.revision);
      if (!result.ok) throw new Error("release_failed");
      if (readRunningGame()?.appid !== stableAppid || deps.runningGameId() !== runningGameId) throw new Error("stale_context");
      setOwner(result);
      if (!await reapplySteamPowerSettings(stableAppid!, runningGameId!)) throw new Error("reapply_failed");
      recordSteamPerformanceDiagnostic("control", { status: "steam_power_reapply_requested" });
    } catch { setFailed(true); }
    finally { mutation.current = false; if (mounted.current) setBusy(false); }
  });
  const status = failed ? "steam.performance.writeFailed" : own ? "steam.performance.owner.pdc"
    : ownershipLost || profile === "unknown" ? "steam.performance.profile.unknown"
      : profile === "game" ? matching ? "steam.performance.profile.game" : "steam.performance.profile.openGame"
        : matching ? "steam.performance.profile.global" : "steam.performance.profile.inactiveGame";
  return <Collapsible id="steam-performance" icon={<LuMonitorCog size={16} />} title={t("steam.performance.title")} summary={own ? "PDC" : profile === "game" ? "Steam" : t("tdp.scope.global")}>
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
      <div role="status" style={{ fontSize: theme.font.caption, color: failed ? theme.color.danger : theme.color.textMuted, lineHeight: 1.4 }}>{t(status)}</div>
      {readable && <SteamPerformanceControls controls={controls}
        disabled={!ready || busy || ownershipPending} onChange={change} />}
      {own && <DialogButton disabled={busy} onClick={() => { void release(); }}>{t("steam.performance.release")}</DialogButton>}
    </div>
  </Collapsible>;
};
