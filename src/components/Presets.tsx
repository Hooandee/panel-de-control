import { FC, memo } from "react";
import { Focusable } from "@decky/ui";
import { LuPencil } from "react-icons/lu";

import { ResolvedPresets, PresetItem } from "../tdp/powerPresets";
import { presetIconNode } from "../tdp/powerPresetIcons";
import { theme } from "../theme";
import { rowChipStyle } from "./chipStyle";

interface PresetsProps {
  resolved: ResolvedPresets;
  editLabel: string;
  hiddenLabel: string; // "Modos ocultos"
  onPick: (item: PresetItem) => void;
  onEdit: () => void; // open the manager modal
}

export const Presets: FC<PresetsProps> = memo(({ resolved, editLabel, hiddenLabel, onPick, onEdit }) => (
  <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8, alignItems: "center" }}>
    {resolved.allHidden ? (
      <Focusable style={{ ...rowChipStyle(false), opacity: 0.65, flex: 1 }} onActivate={onEdit} onClick={onEdit}>
        <LuPencil size={13} />
        <span>{hiddenLabel}</span>
      </Focusable>
    ) : (
      resolved.visible.map((it) => (
        <Focusable key={it.id} style={rowChipStyle(it.active)} onActivate={() => onPick(it)} onClick={() => onPick(it)}>
          {presetIconNode(it.icon, 15)}
          <span>{it.label}</span>
          {it.boost && (
            <span style={{ width: 4, height: 4, borderRadius: 2, background: it.active ? theme.color.accent : theme.color.textMuted }} />
          )}
        </Focusable>
      ))
    )}
    <Focusable aria-label={editLabel} style={{ ...rowChipStyle(false), padding: "6px 8px" }} onActivate={onEdit} onClick={onEdit}>
      <LuPencil size={13} />
    </Focusable>
  </Focusable>
));
