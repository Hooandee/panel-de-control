import { toaster } from "@decky/api";
import { IconType } from "react-icons";
import { LuSun, LuVolume2 } from "react-icons/lu";

import { translate } from "../i18n";
import { theme } from "../theme";
import { toPercent } from "./logic";
import { displayBrightness } from "./display";
import { systemVolume } from "./audio";
import { ScalarControl } from "./types";
import { ScalarKind, lastSelfWrite } from "./selfWrite";
import { readFlag, writeFlag } from "./pdcStorage";
import { shouldSuppress } from "./valueToastLogic";

const KEY = "pdc:valueToast:enabled";
const DEBOUNCE_MS = 900;
const SELF_WINDOW_MS = 1500;
const SILENT_ETYPE = 17;

interface Channel {
  kind: ScalarKind;
  ctrl: ScalarControl;
  labelKey: string;
  color: string;
  Icon: IconType;
}

const CHANNELS: Channel[] = [
  { kind: "volume", ctrl: systemVolume, labelKey: "valueToast.volume", color: theme.color.accent, Icon: LuVolume2 },
  { kind: "brightness", ctrl: displayBrightness, labelKey: "valueToast.brightness", color: theme.color.brightness, Icon: LuSun },
];

let enabled = false;
let alive = false;
let subscribed = false;
const unsubs: Array<() => void> = [];
const timers: Partial<Record<ScalarKind, ReturnType<typeof setTimeout>>> = {};
const lastFraction: Partial<Record<ScalarKind, number>> = {};
const seeded: Partial<Record<ScalarKind, boolean>> = {};
const lastToast: Partial<Record<ScalarKind, ReturnType<typeof toaster.toast>>> = {};

function emitToast(ch: Channel, fraction: number): void {
  const { Icon } = ch;
  const prev = lastToast[ch.kind];
  if (prev) {
    try {
      prev.dismiss();
    } catch {}
  }
  lastToast[ch.kind] = toaster.toast({
    title: translate(ch.labelKey),
    body: (
      <span style={{ fontSize: 18, fontWeight: 700, color: theme.color.textPrimary }}>
        {toPercent(fraction)}%
      </span>
    ),
    icon: <Icon size={22} color={ch.color} />,
    duration: 1500,
    eType: SILENT_ETYPE,
    playSound: false,
    showNewIndicator: false,
  });
}

function onChange(ch: Channel, fraction: number): void {
  if (!seeded[ch.kind]) {
    seeded[ch.kind] = true;
    lastFraction[ch.kind] = fraction;
    return;
  }
  const changed = lastFraction[ch.kind] !== fraction;
  lastFraction[ch.kind] = fraction;
  if (!enabled) return;
  if (!changed) return;
  if (shouldSuppress(lastSelfWrite(ch.kind), Date.now(), SELF_WINDOW_MS)) return;
  const existing = timers[ch.kind];
  if (existing) clearTimeout(existing);
  timers[ch.kind] = setTimeout(() => {
    delete timers[ch.kind];
    emitToast(ch, fraction);
  }, DEBOUNCE_MS);
}

function subscribeAll(): void {
  if (subscribed) return;
  subscribed = true;
  for (const ch of CHANNELS) {
    seeded[ch.kind] = false;
    const unsub = ch.ctrl.subscribe((fraction) => onChange(ch, fraction));
    if (unsub) unsubs.push(unsub);
  }
}

function clearTimers(): void {
  for (const k of Object.keys(timers) as ScalarKind[]) {
    clearTimeout(timers[k]);
    delete timers[k];
  }
}

function teardown(): void {
  for (const u of unsubs.splice(0)) {
    try {
      u();
    } catch {}
  }
  clearTimers();
}

export function isValueToastEnabled(): boolean {
  return readFlag(KEY);
}

export function setValueToastEnabled(on: boolean): void {
  writeFlag(KEY, on);
  enabled = on;
  if (on) {
    if (alive) subscribeAll();
  } else {
    clearTimers();
  }
}

export function startValueToast(): () => void {
  alive = true;
  enabled = isValueToastEnabled();
  if (enabled) subscribeAll();
  return () => {
    alive = false;
    enabled = false;
    teardown();
    subscribed = false;
  };
}
