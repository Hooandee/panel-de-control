import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { EcoState, getEcoState, setEco, setEcoScreen } from "../api";
import { translate } from "../i18n";
import { subscribeActive } from "./activity";
import { displayBrightness } from "./display";
import { hideBlackout, showBlackout } from "./ecoBlackout";
import { startCountdown } from "./ecoCountdown";
import { fromPercent, toPercent } from "./logic";
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

function resetActivity(): void {
  clearTimeout(activityTimer);
  activityTimer = undefined;
  lastInputAt = Number.NEGATIVE_INFINITY;
  inputCount = 0;
  maxInputGap = 0;
}

async function exitForActivity(activity: { duration_ms: number; input_count: number; max_gap_ms: number }): Promise<void> {
  const detail = { reason: "sustained_activity", source: "wake_input", ...activity };
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
      body: translate("system.eco.autoExit"),
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
  enabled = true;
  active = true;
  panel = screenOff;
  wakePct = wake;
  drivenAt = 0;
  addEventListener(INPUT_EVENT, onRawInput);
  unsubscribe = [
    subscribeActive(onSteamActivity),
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
  relapse = undefined;
  stopCountdown();
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
    .then((s) => alive && e === epoch && !exitPending && sync(s))
    .catch(() => {});
  return () => {
    epoch += 1;
    alive = false;
    if (enabled) disable();
  };
}
