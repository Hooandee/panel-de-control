import { getEcoState } from "../api";
import { subscribeActive } from "./activity";
import { displayBrightness } from "./display";
import { fromPercent } from "./logic";
import { ecoBrightness } from "./eco";

// Idle brightness floor while download mode dims the screen. Minimum by default
// (max saving for an unattended download); tune on-device if a fully-dark panel
// reads as "off".
const ECO_FLOOR_PCT = 0;
// Backstop reconcile cadence — runs ONLY while eco is on, to catch a backend B1
// clear (a manual power change that turned eco off without going through the card).
const POLL_MS = 3000;

// Singleton state — this controller runs once at plugin scope (definePlugin), not
// tied to the QAM being open, so the ambient dim works while a game downloads with
// the panel closed. Event-driven (activity transitions) + a backstop poll that runs
// only while enabled; NO render loop.
let enabled = false;
let wakePct = 40;
let alive = false;
let unsubActivity: (() => void) | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
// Bumped on every explicit toggle (hint). An async getEcoState() started before a
// toggle must not reconcile with its now-stale result and undo the user's action.
let epoch = 0;

function drive(active: boolean): void {
  if (enabled) displayBrightness.set(fromPercent(ecoBrightness(active, wakePct, ECO_FLOOR_PCT)));
}

function startPoll(): void {
  if (pollTimer !== null) return;
  pollTimer = setInterval(() => {
    const e = epoch;
    getEcoState()
      .then((s) => {
        if (e === epoch) reconcile(s.enabled, s.wake_brightness); // ignore if a toggle raced
      })
      .catch(() => {
        /* backend busy — retry next tick */
      });
  }, POLL_MS);
}

function stopPoll(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

/** Reconcile to the desired eco state (from a toggle hint, startup, or backstop poll). */
function reconcile(on: boolean, wake: number): void {
  wakePct = wake;
  if (on && !enabled) {
    enabled = true;
    unsubActivity = subscribeActive((active) => drive(active));
    drive(true); // user just enabled it → start at the wake level
    startPoll();
  } else if (!on && enabled) {
    enabled = false;
    if (unsubActivity) {
      unsubActivity();
      unsubActivity = null;
    }
    stopPoll();
    displayBrightness.set(fromPercent(wakePct)); // restore the pre-eco brightness
  }
  // already-on: wake level is snapshotted at enable — nothing to re-drive.
}

/** Instant response when the user toggles download mode from the card. */
export function setEcoActiveHint(on: boolean, wake: number): void {
  epoch += 1; // invalidate any in-flight poll result
  reconcile(on, wake);
}

/** Start the persistent ambient-dim controller. Call once in definePlugin. */
export function startEcoAmbient(): () => void {
  alive = true;
  const e = epoch;
  getEcoState()
    .then((s) => {
      if (alive && e === epoch) reconcile(s.enabled, s.wake_brightness);
    })
    .catch(() => {
      /* backend not ready — a later toggle hint will engage it */
    });
  return () => {
    alive = false;
    stopPoll();
    if (unsubActivity) {
      unsubActivity();
      unsubActivity = null;
    }
    enabled = false;
  };
}
