import { getEcoState } from "../api";
import { subscribeActive } from "./activity";
import { displayBrightness } from "./display";
import { fromPercent, toPercent } from "./logic";
import { activityDebounceMs, ecoBrightness, isDimEcho, isFloorEcho } from "./eco";

// Download-mode ambient dim. Runs at plugin scope so it works with the QAM closed.
const ECO_FLOOR_PCT = 12;
const POLL_MS = 3000;

let enabled = false;
let wakePct = 40;
let alive = false;
let activeState = true;
let unsubActivity: (() => void) | null = null;
let unsubBrightness: (() => void) | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let lastDriven: number | null = null; // last value we drove, to spot our own echoes
let lastDriveAt = 0;
let epoch = 0;

function drive(active: boolean): void {
  if (!enabled) return;
  lastDriven = ecoBrightness(active, wakePct, ECO_FLOOR_PCT);
  lastDriveAt = Date.now();
  displayBrightness.set(fromPercent(lastDriven));
}

function onActivity(active: boolean): void {
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
  if (isFloorEcho(echo, ECO_FLOOR_PCT)) return;
  wakePct = echo;
}

function startPoll(): void {
  if (pollTimer !== null) return;
  pollTimer = setInterval(() => {
    const e = epoch;
    getEcoState()
      .then((s) => {
        if (e === epoch) reconcile(s.enabled, s.wake_brightness);
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
  stopPoll();
}

function reconcile(on: boolean, wake: number): void {
  if (on && !enabled) {
    wakePct = wake; // snapshot only on enable; while on, wakePct tracks the user
    enabled = true;
    // Dim to the floor immediately on enable, not only once idle. activeState stays
    // true so the "active" signal fired while still in the menu doesn't bounce it back
    // to full; a later idle→active transition still wakes it.
    activeState = true;
    drive(false);
    unsubActivity = subscribeActive(onActivity);
    unsubBrightness = displayBrightness.subscribe(onBrightness);
    startPoll();
  } else if (!on && enabled) {
    enabled = false;
    teardown();
    displayBrightness.set(fromPercent(wakePct));
  }
}

export function setEcoActiveHint(on: boolean, wake: number): void {
  epoch += 1;
  reconcile(on, wake);
}

export function startEcoAmbient(): () => void {
  alive = true;
  const e = epoch;
  getEcoState()
    .then((s) => {
      if (alive && e === epoch) reconcile(s.enabled, s.wake_brightness);
    })
    .catch(() => {});
  return () => {
    alive = false;
    if (enabled) displayBrightness.set(fromPercent(wakePct)); // don't leave the panel dim
    enabled = false;
    teardown();
  };
}
