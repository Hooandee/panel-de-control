import { addEventListener, removeEventListener } from "@decky/api";
import { getEcoState, setEcoScreen } from "../api";
import { translate } from "../i18n";
import { subscribeActive } from "./activity";
import { displayBrightness } from "./display";
import { hideBlackout, showBlackout } from "./ecoBlackout";
import { Countdown, startCountdown } from "./ecoCountdown";
import { fromPercent, toPercent } from "./logic";
import { activityDebounceMs, ecoBrightness, isDimEcho, isFloorEcho } from "./eco";

// Download mode's screen. Runs at plugin scope so it works with the QAM closed.
// "panel": gamescope switches the internal panel off. "blackout": black layer over
// Steam's UI plus minimum brightness, for gamescope builds without that control.
type ScreenMode = "panel" | "blackout";

const BLACKOUT_FLOOR_PCT = 0;
const POLL_MS = 3000;
const COUNTDOWN_S = 3;
// The backend reports raw input at once; idleness is Steam's call alone, since Steam reads
// every control on every handheld. If Steam never reports an input the backend saw, go
// dark again after this long.
const RELAPSE_MS = 8000;
const ACTIVITY_EVENT = "pdc_eco_activity";

let enabled = false;
let mode: ScreenMode = "blackout";
let wakePct = 40;
let alive = false;
let activeState = true;
let unsubActivity: (() => void) | null = null;
let unsubBrightness: (() => void) | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let lastDriven: number | null = null; // last brightness we drove, to spot our own echoes
let lastDriveAt = 0;
let epoch = 0;
let countdown: Countdown | null = null;
let relapseTimer: ReturnType<typeof setTimeout> | null = null;

function wakeFromLayer(): void {
  onBackendActivity(true);
}

function driveBlackout(active: boolean): void {
  if (active) hideBlackout();
  else showBlackout(wakeFromLayer);
  lastDriven = ecoBrightness(active, wakePct, BLACKOUT_FLOOR_PCT);
  lastDriveAt = Date.now();
  displayBrightness.set(fromPercent(lastDriven));
}

function goDark(): void {
  if (mode === "blackout") {
    driveBlackout(false);
    return;
  }
  // Catches the tap that wakes the panel so it never lands on a control underneath.
  showBlackout(wakeFromLayer);
  const e = epoch;
  setEcoScreen(true)
    .then((r) => {
      if (r.ok || !enabled || e !== epoch) return;
      if (activeState) {
        hideBlackout();
        return;
      }
      // A panel that could not be confirmed off falls back to the black layer.
      mode = "blackout";
      driveBlackout(false);
    })
    .catch(() => {});
}

function goLight(): void {
  if (mode === "blackout") {
    driveBlackout(true);
    return;
  }
  hideBlackout();
  setEcoScreen(false).catch(() => {});
}

function cancelCountdown(): void {
  countdown?.cancel();
  countdown = null;
}

function clearRelapse(): void {
  if (relapseTimer !== null) {
    clearTimeout(relapseTimer);
    relapseTimer = null;
  }
}

function drive(active: boolean): void {
  if (!enabled) return;
  cancelCountdown();
  if (active) {
    goLight();
    return;
  }
  countdown = startCountdown(COUNTDOWN_S, translate("system.eco.countdown"), () => {
    countdown = null;
    if (enabled && !activeState) goDark();
  });
}

function onBackendActivity(active: boolean): void {
  if (!enabled || !active) return;
  if (mode === "panel") hideBlackout();
  if (activeState) return;
  clearRelapse();
  activeState = true;
  drive(true);
  relapseTimer = setTimeout(() => {
    relapseTimer = null;
    if (enabled && activeState) {
      activeState = false;
      drive(false);
    }
  }, RELAPSE_MS);
}

function onActivity(active: boolean): void {
  clearRelapse();
  if (debounceTimer !== null) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    if (active !== activeState) {
      activeState = active;
      drive(active);
    }
  }, activityDebounceMs(active));
}

// Adopt a user brightness change as the new wake level; skip our own echoes and the floor.
function onBrightness(fraction: number): void {
  if (!enabled) return;
  const echo = toPercent(fraction);
  if (isDimEcho(echo, lastDriven, Date.now() - lastDriveAt)) return;
  if (isFloorEcho(echo, BLACKOUT_FLOOR_PCT)) return;
  wakePct = echo;
}

function startPoll(): void {
  if (pollTimer !== null) return;
  pollTimer = setInterval(() => {
    const e = epoch;
    getEcoState()
      .then((s) => {
        if (e !== epoch) return;
        reconcile(s.enabled, s.wake_brightness, s.screen_off);
        // A lit panel never keeps the catch layer, whatever event was missed.
        if (enabled && mode === "panel" && !s.screen_asleep && activeState && !countdown) hideBlackout();
      })
      .catch(() => {});
  }, POLL_MS);
}

function stopPoll(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function teardown(): void {
  if (unsubActivity) {
    unsubActivity();
    unsubActivity = null;
  }
  if (unsubBrightness) {
    unsubBrightness();
    unsubBrightness = null;
  }
  if (debounceTimer !== null) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }
  removeEventListener(ACTIVITY_EVENT, onBackendActivity);
  cancelCountdown();
  clearRelapse();
  stopPoll();
}

function restoreScreen(): void {
  hideBlackout();
  if (mode === "panel") setEcoScreen(false).catch(() => {});
  if (lastDriven !== null) displayBrightness.set(fromPercent(wakePct));
  lastDriven = null;
}

function reconcile(on: boolean, wake: number, screenOff: boolean): void {
  if (on && !enabled) {
    wakePct = wake; // snapshot only on enable; while on, wakePct tracks the user
    mode = screenOff ? "panel" : "blackout";
    enabled = true;
    // The screen goes dark on Steam's next idle signal, not instantly: an input made
    // while the user is still active would otherwise produce no idle→active wake.
    activeState = true;
    unsubActivity = subscribeActive(onActivity);
    unsubBrightness = displayBrightness.subscribe(onBrightness);
    addEventListener(ACTIVITY_EVENT, onBackendActivity);
    startPoll();
  } else if (!on && enabled) {
    enabled = false;
    teardown();
    restoreScreen();
  }
}

export function setEcoActiveHint(on: boolean, wake: number, screenOff: boolean): void {
  epoch += 1;
  reconcile(on, wake, screenOff);
}

export function startEcoAmbient(): () => void {
  alive = true;
  const e = epoch;
  getEcoState()
    .then((s) => {
      if (!alive || e !== epoch) return;
      reconcile(s.enabled, s.wake_brightness, s.screen_off);
    })
    .catch(() => {});
  return () => {
    alive = false;
    if (enabled) restoreScreen(); // don't leave the panel dark
    enabled = false;
    teardown();
  };
}
