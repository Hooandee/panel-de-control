import { DialogButton, Focusable } from "@decky/ui";
import { FC, useEffect, useState } from "react";
import { LuClapperboard, LuX } from "react-icons/lu";

import { accessoryDemo, stopAccessoryDemo } from "../api";
import { useI18n } from "../i18n";
import { demoArt } from "./demoArt";
import { decodeFrames, DecodedFrames } from "./pixelFrames";

export interface DemoState {
  shot: string;
  index: number;
  total: number;
  frames: DecodedFrames;
}

let current: DemoState | null = null;
const listeners = new Set<() => void>();
const publish = (next: DemoState | null) => {
  current = next;
  listeners.forEach((listener) => listener());
};

/** The demo shot on screen; kept outside React because Steam unmounts the panel under modals. */
export function useDemo(): DemoState | null {
  const [, force] = useState(0);
  useEffect(() => {
    const listener = () => force((n) => n + 1);
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, []);
  return current;
}

export function clearDemo(): void {
  publish(null);
}

export const DemoBar: FC<{ active: boolean; onStopped: () => void }> = ({ active, onStopped }) => {
  const { t } = useI18n();
  const demo = useDemo();
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!active && current) publish(null); }, [active]);

  const next = () => {
    if (busy) return;
    setBusy(true);
    void demoArt()
      .then((art) => accessoryDemo(art))
      .then((shot) => {
        if (shot?.frames) publish({ shot: shot.shot, index: shot.index, total: shot.total, frames: decodeFrames(shot) });
      })
      .catch(() => undefined)
      .finally(() => setBusy(false));
  };
  const stop = () => {
    publish(null);
    void stopAccessoryDemo().then(onStopped).catch(() => undefined);
  };

  return (
    <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
      <DialogButton onClick={next} onOKButton={next} disabled={busy}
        style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontWeight: 750 }}>
        <LuClapperboard />
        {demo ? `${demo.index + 1}/${demo.total} · ${t(`accessories.demo.${demo.shot}`)}` : t("accessories.demo.start")}
      </DialogButton>
      {demo && (
        <DialogButton onClick={stop} onOKButton={stop} aria-label={t("accessories.demo.stop")}
          style={{ minWidth: 0, width: 44, padding: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <LuX />
        </DialogButton>
      )}
    </Focusable>
  );
};
