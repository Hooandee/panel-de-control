import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { EcoState, getEcoState, setEco, setEcoScreen } from "../api";
import { callBackend } from "../deckyInternal";
import { translate } from "../i18n";
import { subscribeActive } from "./activity";
import { COLORES_PLUGIN_NAME, isColoresInstalled } from "./colores";
import { displayBrightness } from "./display";
import { subscribeDownloadActive } from "./downloads";
import { hideBlackout, showBlackout } from "./ecoBlackout";
import { startCountdown } from "./ecoCountdown";
import { fromPercent, toPercent } from "./logic";
import { hydratePrefs, readString, removeString, writeString } from "./pdcStorage";
import { recordUiEvent } from "./uiEvents";

// Download mode's screen, at plugin scope so it works with the QAM closed. Panel mode:
// gamescope switches the internal panel off. Otherwise a black layer at minimum brightness.
// Idleness is Steam's call (it reads every control on every handheld); the backend reports
// raw input at once so waking is instant.
const POLL_MS = 3000;
const COUNTDOWN_S = 3;
const WAKE_DEBOUNCE_MS = 150;
// Raw input Steam never saw gets no idle signal after it: go dark again after this long.
const RELAPSE_MS = 8000;
const AUTO_EXIT_MS = 10000;
const INPUT_GAP_MS = 4000;
const TIMER_LATENESS_MS = 1000;
const EXIT_TIMEOUT_MS = 10000;
// Steam's queue goes idle for a moment between two downloads.
const DOWNLOAD_END_GRACE_MS = 30000;
const INPUT_EVENT = "pdc_eco_input";

let enabled = false;
let alive = false;
let panel = false;
let active = true;
let wakePct = 40;
let drivenAt = 0;
let epoch = 0;
let cancelCountdown: (() => void) | null = null;
let relapse: ReturnType<typeof setTimeout> | undefined;
let debounce: ReturnType<typeof setTimeout> | undefined;
let poll: ReturnType<typeof setInterval> | undefined;
let activityTimer: ReturnType<typeof setTimeout> | undefined;
let lastInputAt = Number.NEGATIVE_INFINITY;
let exitPending = false;
let inputCount = 0;
let maxInputGap = 0;
let unsubscribe: (() => void)[] = [];
let sawDownload = false;
let downloadEnd: ReturnType<typeof setTimeout> | undefined;

// Download mode also dims the joystick RGB through the sibling Colores plugin:
// lights go out with the screen and come back on wake or when download mode ends.
// We snapshot Colores' power flag into durable storage so a reboot or a crash
// cannot leave the lights stuck off. Every degradation path (Colores absent,
// RPC failure, unknown state) leaves RGB alone. Dim and restore share one queue
// so a wake in the same tick as a dim cannot finish with the lights off.

const RGB_SNAPSHOT_KEY = "pdc:ecoRgbSnapshot";
let rgbOff = false; // synchronous intent, set before any await
let rgbChain: Promise<void> = Promise.resolve();

function coloresCall(method: string, ...args: unknown[]): Promise<unknown> {
  return callBackend("loader/call_plugin_method", COLORES_PLUGIN_NAME, method, ...args);
}

function enqueueRgb(task: () => Promise<void>): void {
  rgbChain = rgbChain.then(task, task).catch(() => {});
}

function rgbGoDark(): void {
  // A stored snapshot means the lights are already intentionally off (e.g. a
  // previous session) — don't overwrite the original value with "off".
  if (!isColoresInstalled() || rgbOff || readString(RGB_SNAPSHOT_KEY) !== null) return;
  rgbOff = true; // reserve the intent now, so a wake in the same tick restores
  enqueueRgb(async () => {
    try {
      const state = await coloresCall("get_state");
      if (!rgbOff) return; // a wake/close superseded us while reading
      const power = (state as { power?: unknown } | null)?.power;
      if (typeof power !== "boolean" || !power) {
        rgbOff = false; // already off / unknown shape: nothing to snapshot or restore
        return;
      }
      writeString(RGB_SNAPSHOT_KEY, "1"); // Colores' power was on; remember that
      await coloresCall("set_power", false);
    } catch {
      if (rgbOff) { rgbOff = false; removeString(RGB_SNAPSHOT_KEY); }
    }
  });
}

function rgbRestore(): void {
  rgbOff = false;
  enqueueRgb(async () => {
    await hydratePrefs(); // pull the durable snapshot if this is a freshly booted session
    const saved = readString(RGB_SNAPSHOT_KEY);
    if (saved === null) return; // RGB was never dimmed by us
    removeString(RGB_SNAPSHOT_KEY);
    if (!isColoresInstalled()) return;
    try { await coloresCall("set_power", saved === "1"); } catch {}
  });
}

function resetActivity(): void {
  clearTimeout(activityTimer);
  activityTimer = undefined;
  lastInputAt = Number.NEGATIVE_INFINITY;
  inputCount = 0;
  maxInputGap = 0;
}

async function exitEco(detail: Record<string, unknown>, toastKey: string): Promise<void> {
  const e = ++epoch;
  exitPending = true;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    const state = await Promise.race([
      setEco(false, wakePct),
      new Promise<never>((_, reject) => {
        timeout = setTimeout(() => reject(new Error("eco_exit_timeout")), EXIT_TIMEOUT_MS);
      }),
    ]);
    recordUiEvent("system", "eco_auto_exit", detail, !state.enabled);
    if (!alive || e !== epoch || state.enabled) return;
    disable();
    toaster.toast({
      title: translate("system.eco.title"),
      body: translate(toastKey),
      duration: 3000,
      playSound: false,
      showNewIndicator: false,
    });
  } catch {
    recordUiEvent("system", "eco_auto_exit", detail, false);
  } finally {
    clearTimeout(timeout);
    if (e === epoch) exitPending = false;
  }
}

function exitForActivity(activity: { duration_ms: number; input_count: number; max_gap_ms: number }): Promise<void> {
  return exitEco({ reason: "sustained_activity", source: "wake_input", ...activity }, "system.eco.autoExit");
}

function onDownloadActive(active: boolean): void {
  clearTimeout(downloadEnd);
  downloadEnd = undefined;
  if (active) {
    sawDownload = true;
    return;
  }
  if (!sawDownload) return;
  downloadEnd = setTimeout(() => {
    downloadEnd = undefined;
    if (alive && enabled && !exitPending) void exitEco({ reason: "download_finished", source: "steam_downloads" }, "system.eco.downloadDone");
  }, DOWNLOAD_END_GRACE_MS);
}

function recordActivity(): void {
  if (exitPending) return;
  const now = Date.now();
  if (now - lastInputAt >= INPUT_GAP_MS) resetActivity();
  if (Number.isFinite(lastInputAt)) maxInputGap = Math.max(maxInputGap, now - lastInputAt);
  inputCount += 1;
  lastInputAt = now;
  if (activityTimer !== undefined) return;
  const deadline = now + AUTO_EXIT_MS;
  activityTimer = setTimeout(() => {
    activityTimer = undefined;
    const now = Date.now();
    if (!alive || !enabled || now - lastInputAt >= INPUT_GAP_MS
      || now < deadline || now - deadline > TIMER_LATENESS_MS) {
      resetActivity();
      return;
    }
    const activity = { duration_ms: now - (deadline - AUTO_EXIT_MS), input_count: inputCount, max_gap_ms: maxInputGap };
    resetActivity();
    void exitForActivity(activity);
  }, AUTO_EXIT_MS);
}

function setBrightness(pct: number): void {
  drivenAt = Date.now();
  displayBrightness.set(fromPercent(pct));
}

function goDark(): void {
  rgbGoDark(); // joystick lights go out together with the screen
  // The layer also catches the tap that wakes a sleeping panel, so it never presses anything.
  showBlackout(onRawInput);
  if (!panel) {
    setBrightness(0);
    return;
  }
  const e = epoch;
  setEcoScreen(true)
    .then((r) => {
      if (r.ok || !enabled || e !== epoch) return;
      if (active) {
        hideBlackout();
        return;
      }
      panel = false; // not confirmed off: black layer instead
      setBrightness(0);
    })
    .catch(() => {});
}

function goLight(): void {
  rgbRestore(); // joystick lights come back on wake
  hideBlackout();
  if (panel) setEcoScreen(false).catch(() => {});
  else setBrightness(wakePct);
}

function stopCountdown(): void {
  cancelCountdown?.();
  cancelCountdown = null;
}

function setActive(next: boolean): void {
  if (!enabled || next === active) return;
  active = next;
  stopCountdown();
  if (next) {
    goLight();
    return;
  }
  cancelCountdown = startCountdown(COUNTDOWN_S, translate("system.eco.countdown"), () => {
    cancelCountdown = null;
    if (enabled && !active) goDark();
  });
}

function armRelapse(): void {
  clearTimeout(relapse);
  relapse = setTimeout(() => {
    relapse = undefined;
    setActive(false);
  }, RELAPSE_MS);
}

function onRawInput(): void {
  if (!enabled) return;
  recordActivity();
  if (panel) hideBlackout();
  if (active) {
    // Input Steam does not count keeps the screen on while it continues.
    if (relapse !== undefined) armRelapse();
    return;
  }
  setActive(true);
  armRelapse();
}

function onSteamActivity(next: boolean): void {
  if (!next) resetActivity();
  clearTimeout(relapse);
  relapse = undefined;
  clearTimeout(debounce);
  debounce = setTimeout(() => setActive(next), next ? WAKE_DEBOUNCE_MS : 0);
}

// A brightness the user picks while lit is the level to wake back to.
function onBrightness(fraction: number): void {
  if (enabled && active && !panel && Date.now() - drivenAt > 2000) wakePct = toPercent(fraction);
}

function enable(wake: number, screenOff: boolean): void {
  resetActivity();
  exitPending = false;
  sawDownload = false;
  enabled = true;
  active = true;
  panel = screenOff;
  wakePct = wake;
  drivenAt = 0;
  addEventListener(INPUT_EVENT, onRawInput);
  unsubscribe = [
    subscribeActive(onSteamActivity),
    subscribeDownloadActive(onDownloadActive),
    displayBrightness.subscribe(onBrightness),
    () => removeEventListener(INPUT_EVENT, onRawInput),
  ].filter((u): u is () => void => u !== null);
  poll = setInterval(() => {
    if (exitPending) return;
    const e = epoch;
    getEcoState()
      .then((s) => alive && e === epoch && !exitPending && sync(s))
      .catch(() => {});
  }, POLL_MS);
}

function disable(): void {
  resetActivity();
  exitPending = false;
  enabled = false;
  unsubscribe.forEach((u) => u());
  unsubscribe = [];
  clearInterval(poll);
  clearTimeout(debounce);
  clearTimeout(relapse);
  clearTimeout(downloadEnd);
  downloadEnd = undefined;
  relapse = undefined;
  stopCountdown();
  rgbRestore(); // joystick lights come back when download mode closes
  hideBlackout();
  if (panel) setEcoScreen(false).catch(() => {});
  else setBrightness(wakePct);
}

// The backend wins over whatever this controller believes, whatever event was missed.
function sync(s: EcoState): void {
  if (!s.enabled) {
    if (enabled) disable();
    return;
  }
  if (!enabled) {
    enable(s.wake_brightness, s.screen_off);
    goLight(); // a running session picked up after a reload starts lit
    return;
  }
  if (!active || cancelCountdown) return;
  if (!panel && s.screen_off) panel = true; // panel power became available
  if (panel) {
    hideBlackout();
    if (s.screen_asleep) setEcoScreen(false).catch(() => {});
  }
}

export function setEcoActiveHint(on: boolean, wake: number, screenOff: boolean): void {
  epoch += 1;
  resetActivity();
  exitPending = false;
  if (on && !enabled) enable(wake, screenOff);
  else if (!on && enabled) disable();
}

export function startEcoAmbient(): () => void {
  alive = true;
  const e = epoch;
  getEcoState()
    .then((s) => {
      if (!alive || e !== epoch || exitPending) return;
      // A crash/reboot while download mode held the lights off leaves a durable
      // snapshot. If we are not resuming download mode, put the lights back now.
      if (!s.enabled) rgbRestore();
      sync(s);
    })
    .catch(() => {});
  return () => {
    epoch += 1;
    alive = false;
    if (enabled) disable();
  };
}
