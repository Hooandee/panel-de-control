import { FC, useState } from "react";
import { Focusable, ModalRoot, SliderField, TextField, showModal } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Rgb, hexToRgb, normalizeHex, rgbToHex } from "../mangohud/model";

// The Steam CEF native <input type=color> does nothing (MangoPeel hit the same
// wall), so colours are picked with RGB sliders + a hex field in a modal. Live:
// each channel change pushes the new colour up so the HUD preview updates as you
// drag. Pure colour maths live in model.ts (unit-tested).

const CHANNELS: { key: keyof Rgb; labelKey: string }[] = [
  { key: "r", labelKey: "hud.color.r" },
  { key: "g", labelKey: "hud.color.g" },
  { key: "b", labelKey: "hud.color.b" },
];

const ColorModalBody: FC<{ label: string; initial: string; onChange: (hex: string) => void }> = ({ label, initial, onChange }) => {
  const { t } = useI18n();
  const [rgb, setRgb] = useState<Rgb>(hexToRgb(initial));
  const [hexText, setHexText] = useState<string>(normalizeHex(initial) ?? "ffffff");
  const hex = rgbToHex(rgb);

  const setChannel = (key: keyof Rgb, v: number) => {
    const next = { ...rgb, [key]: v };
    setRgb(next);
    const h = rgbToHex(next);
    setHexText(h);
    onChange(h);
  };
  const onHexInput = (raw: string) => {
    setHexText(raw);
    const clean = normalizeHex(raw);
    if (clean) {
      setRgb(hexToRgb(clean));
      onChange(clean);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm, maxWidth: 520, margin: "0 auto", width: "100%" }}>
      <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{label}</div>
      <div
        style={{
          height: 56, borderRadius: theme.radius.md, background: `#${hex}`,
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        }}
      />
      {CHANNELS.map(({ key, labelKey }) => (
        <SliderField
          key={key}
          label={t(labelKey)}
          value={rgb[key]}
          min={0}
          max={255}
          step={1}
          showValue
          onChange={(v) => setChannel(key, v)}
        />
      ))}
      <TextField label={t("hud.color.hex")} value={hexText} onChange={(e) => onHexInput(e.target.value)} />
    </div>
  );
};

const ColorModal: FC<{ label: string; initial: string; onChange: (hex: string) => void; closeModal?: () => void }> = ({ label, initial, onChange, closeModal }) => (
  <ModalRoot closeModal={closeModal}>
    <ColorModalBody label={label} initial={initial} onChange={onChange} />
  </ModalRoot>
);

/** A colour swatch button; tapping it opens the RGB/hex modal. `value`/`onChange`
 *  are 6-digit hex without '#'. Changes stream live while the modal is open. */
export const ColorPicker: FC<{ label: string; value: string; onChange: (hex: string) => void; size?: number }> = ({ label, value, onChange, size = 28 }) => (
  <Focusable
    onActivate={() => showModal(<ColorModal label={label} initial={value} onChange={onChange} />)}
    onClick={() => showModal(<ColorModal label={label} initial={value} onChange={onChange} />)}
    aria-label={label}
    title={label}
    style={{
      width: size, height: size, flexShrink: 0, borderRadius: 6, cursor: "pointer",
      background: `#${value}`, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    }}
  >
    <span />
  </Focusable>
);
