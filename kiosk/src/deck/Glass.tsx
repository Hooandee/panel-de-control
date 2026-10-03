import { CSSProperties, FC, PointerEvent, ReactNode, useEffect, useState } from "react";

import { clamp01, stepAt } from "./deckMath";

const CLOSE_MS = 320;

/** Keeps a dialog mounted through its closing animation. */
export function usePresence<T>(value: T | null): { shown: T | null; visible: boolean } {
  const [shown, setShown] = useState<T | null>(value);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (value != null) {
      setShown(value);
      const frame = requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
      return () => cancelAnimationFrame(frame);
    }
    setVisible(false);
    const timer = window.setTimeout(() => setShown(null), CLOSE_MS);
    return () => window.clearTimeout(timer);
  }, [value]);
  return { shown, visible };
}

export const GlassDialog: FC<{ visible: boolean; onClose: () => void; children: ReactNode }> = ({ visible, onClose, children }) => (
  <>
    <div className={`g-scrim${visible ? " is-on" : ""}`} onClick={onClose} />
    <div className={`g-glass${visible ? " is-on" : ""}`} role="dialog">
      {children}
    </div>
  </>
);

export const Hero: FC<{ bubble: ReactNode; title: ReactNode; detail?: ReactNode; bubbleStyle?: CSSProperties }> = ({
  bubble, title, detail, bubbleStyle,
}) => (
  <div className="g-hero">
    <div className="g-bubble" style={bubbleStyle}>{bubble}</div>
    <div>
      <b>{title}</b>
      {detail && <span>{detail}</span>}
    </div>
  </div>
);

export const Orb: FC<{ on?: boolean; disabled?: boolean; label: ReactNode; onPress: () => void; children: ReactNode }> = ({
  on, disabled, label, onPress, children,
}) => (
  <button type="button" className={`g-orb${on ? " is-on" : ""}`} disabled={disabled} aria-pressed={Boolean(on)} onClick={onPress}>
    <i>{children}</i>
    {label}
  </button>
);

export const Orbs: FC<{ scroll?: boolean; children: ReactNode }> = ({ scroll, children }) => (
  <div className={`g-orbs${scroll ? " is-scroll" : ""}`}>{children}</div>
);

const STEP_PAD = 11;

/** Discrete horizontal slider: follows the finger, commits on release. */
export const Steps: FC<{ value: number; min: number; max: number; disabled?: boolean; onCommit: (value: number) => void }> = ({
  value, min, max, disabled, onCommit,
}) => {
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? value;
  const fraction = max > min ? (shown - min) / (max - min) : 0;
  const at = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    return stepAt(event.clientX - box.left, box.width, STEP_PAD, min, max);
  };
  const position = `calc(${STEP_PAD}px + (100% - ${2 * STEP_PAD}px) * ${fraction})`;
  return (
    <div
      className={`g-steps${drag != null ? " is-drag" : ""}${disabled ? " is-off" : ""}`}
      onPointerDown={(event) => {
        if (disabled) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        setDrag(at(event));
      }}
      onPointerMove={(event) => {
        if (drag != null) setDrag(at(event));
      }}
      onPointerUp={() => {
        if (drag != null && drag !== value) onCommit(drag);
        setDrag(null);
      }}
      onPointerCancel={() => setDrag(null)}
    >
      <div className="g-steps-track" />
      <div className="g-steps-fill" style={{ width: `calc((100% - ${2 * STEP_PAD}px) * ${fraction})` }} />
      <div className="g-steps-knob" style={{ left: position }} />
    </div>
  );
};

type Axis = "x" | "y";

function useDrag(axis: Axis, value: number | null, onChange: (value: number) => void, onCommit?: (value: number) => void) {
  const [drag, setDrag] = useState<number | null>(null);
  const at = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    return clamp01(axis === "y" ? (box.bottom - event.clientY) / box.height : (event.clientX - box.left) / box.width);
  };
  const move = (next: number) => {
    setDrag(next);
    onChange(next);
  };
  return {
    shown: drag ?? value,
    dragging: drag != null,
    handlers: {
      onPointerDown: (event: PointerEvent<HTMLDivElement>) => {
        if (value == null) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        move(at(event));
      },
      onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
        if (drag != null) move(at(event));
      },
      onPointerUp: () => {
        if (drag != null) onCommit?.(drag);
        setDrag(null);
      },
      onPointerCancel: () => setDrag(null),
    },
  };
}

/** Control Center–style tall slider; `value` null means Steam has not reported it yet. */
export const VFader: FC<{
  value: number | null;
  icon: ReactNode;
  label: string;
  className: string;
  onChange: (value: number) => void;
  onCommit: (value: number) => void;
}> = ({ value, icon, label, className, onChange, onCommit }) => {
  const { shown, dragging, handlers } = useDrag("y", value, onChange, onCommit);
  return (
    <div
      className={`g-vfader ${className}${dragging ? " is-drag" : ""}${value == null ? " is-off" : ""}`}
      role="slider"
      aria-label={label}
      aria-valuenow={shown == null ? undefined : Math.round(shown * 100)}
      {...handlers}
    >
      <div className="g-vfader-fill" style={{ height: `${(shown ?? 0) * 100}%` }} />
      {icon}
    </div>
  );
};

export const HBar: FC<{
  value: number | null;
  icon: ReactNode;
  label: string;
  onChange?: (value: number) => void;
  onCommit: (value: number) => void;
}> = ({ value, icon, label, onChange = () => {}, onCommit }) => {
  const { shown, handlers } = useDrag("x", value, onChange, onCommit);
  const pct = Math.round((shown ?? 0) * 100);
  return (
    <div className={`g-hbar${value == null ? " is-off" : ""}`} role="slider" aria-label={label} aria-valuenow={pct} {...handlers}>
      <div className="g-hbar-fill" style={{ width: `${pct}%` }} />
      {icon}
      <span className="g-hbar-pct">{pct} %</span>
    </div>
  );
};

export const Chips: FC<{ items: { id: string; label: string }[]; selected: string | null; onPick: (id: string) => void }> = ({
  items, selected, onPick,
}) => (
  <div className="g-chips">
    {items.map((item) => (
      <button key={item.id} type="button" className={item.id === selected ? "is-on" : undefined} onClick={() => onPick(item.id)}>
        {item.label}
      </button>
    ))}
  </div>
);
