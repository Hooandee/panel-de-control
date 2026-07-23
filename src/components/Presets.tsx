import { FC, memo } from "react";
import { Focusable } from "@decky/ui";
import { LuPlus } from "react-icons/lu";

import { ResolvedPresets, PresetItem, presetTitle, presetSub } from "../tdp/powerPresets";
import { presetIconNode } from "../tdp/powerPresetIcons";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { iconChipStyle, rowChipStyle } from "./chipStyle";

interface PresetsProps {
  resolved: ResolvedPresets;
  manageLabel: string; // "Añadir / editar"
  hiddenLabel: string; // "Modos ocultos"
  onPick: (item: PresetItem) => void;
  onEdit: () => void; // open the manager modal
}

// A boost dot only for presets that actually add headroom (auto/custom), not flat.
const hasBoost = (it: PresetItem) => it.boost != null && it.boost.mode !== "estable";

const BoostDot: FC<{ active: boolean }> = ({ active }) => (
  <span style={{ width: 4, height: 4, borderRadius: 2, background: active ? theme.color.accent : theme.color.textMuted }} />
);

export const Presets: FC<PresetsProps> = memo(({ resolved, manageLabel, hiddenLabel, onPick, onEdit }) => {
  const { t } = useI18n();
  const title = (it: PresetItem) => presetTitle(it, t);
  const sub = presetSub;
  // Three or fewer visible presets read better as big column tiles; more wrap compactly.
  const big = resolved.visible.length <= 3;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
      {resolved.allHidden ? (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, textAlign: "center", padding: "4px 0" }}>
          {hiddenLabel}
        </div>
      ) : big ? (
        <Focusable style={{ display: "flex", gap: 6 }}>
          {resolved.visible.map((it) => (
            <Focusable key={it.id} style={iconChipStyle(it.active)} onActivate={() => onPick(it)} onClick={() => onPick(it)}>
              {presetIconNode(it.icon, 20)}
              <span style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 600, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {title(it)}
                {hasBoost(it) && <BoostDot active={it.active} />}
              </span>
              {sub(it) && <span style={{ color: theme.color.textMuted }}>{sub(it)}</span>}
            </Focusable>
          ))}
        </Focusable>
      ) : (
        <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          {resolved.visible.map((it) => (
            <Focusable key={it.id} style={rowChipStyle(it.active)} onActivate={() => onPick(it)} onClick={() => onPick(it)}>
              {presetIconNode(it.icon, 15)}
              <span>{title(it)}</span>
              {sub(it) && <span style={{ color: theme.color.textMuted }}>{sub(it)}</span>}
              {hasBoost(it) && <BoostDot active={it.active} />}
            </Focusable>
          ))}
        </Focusable>
      )}
      <Focusable
        aria-label={manageLabel}
        style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          padding: "6px 10px", borderRadius: theme.radius.sm,
          background: theme.color.surfaceRaised,
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
          color: theme.color.textPrimary, fontSize: theme.font.caption, cursor: "pointer",
        }}
        onActivate={onEdit}
        onClick={onEdit}
      >
        <LuPlus size={14} /> {manageLabel}
      </Focusable>
    </div>
  );
});
