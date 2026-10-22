import { Focusable } from "@decky/ui";
import { FC, useEffect, useMemo, useState } from "react";

import type { AccessorySceneMeta } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import type { Block } from "./ComposerModal";
import { MyCreations } from "./MyCreations";
import { DecodedFrames } from "./pixelFrames";
import { PixelPreview } from "./PixelPreview";
import { loadPreview } from "./useAccessories";
import { tileStyle, OnPanelDot } from "./tiles";

const TILE_PITCH = 1.75;
const CHIPS_PER_ROW = 3;

const SceneTile: FC<{ scene: AccessorySceneMeta; selected: boolean; onPanel: boolean; onPick: () => void }> = ({ scene, selected, onPanel, onPick }) => {
  const { t } = useI18n();
  const [decoded, setDecoded] = useState<DecodedFrames | null>(null);
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    let live = true;
    void loadPreview(scene.id).then((value) => { if (live) setDecoded(value); });
    return () => { live = false; };
  }, [scene.id]);
  return (
    <Focusable onActivate={onPick} onClick={onPick} onGamepadFocus={() => setFocused(true)} onGamepadBlur={() => setFocused(false)}
      onOKActionDescription={t("accessories.action.preview")} style={tileStyle(focused, selected)}>
      <PixelPreview decoded={decoded} pitch={TILE_PITCH} animate={focused} label={t(scene.labelKey)} />
      <div style={{ display: "flex", alignItems: "center", gap: 5, width: "100%", justifyContent: "center", minWidth: 0 }}>
        {onPanel && <OnPanelDot />}
        <span style={{ fontSize: theme.font.caption, fontWeight: 650, color: selected || focused ? theme.color.textPrimary : theme.color.textMuted,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t(scene.labelKey)}</span>
      </div>
    </Focusable>
  );
};

const CategoryChip: FC<{ label: string; selected: boolean; onPick: () => void }> = ({ label, selected, onPick }) => {
  const [focused, setFocused] = useState(false);
  return (
    <Focusable onActivate={onPick} onClick={onPick} onGamepadFocus={() => { setFocused(true); onPick(); }}
      onGamepadBlur={() => setFocused(false)}
      style={{ flex: 1, minWidth: 0, textAlign: "center", padding: "7px 4px", borderRadius: 999, fontSize: theme.font.caption, fontWeight: 700,
        background: selected ? theme.color.selectedFill : "rgba(255,255,255,0.06)",
        color: selected ? theme.color.onAccent : theme.color.textPrimary,
        boxShadow: focused ? `0 0 0 2px ${theme.color.surface}, 0 0 0 4px ${theme.color.accent}` : "none",
        transform: focused ? "scale(1.05)" : "scale(1)", transition: "transform 120ms ease, box-shadow 120ms ease",
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
      {label}
    </Focusable>
  );
};

export const SceneGallery: FC<{
  catalog: AccessorySceneMeta[];
  selectedScene: string;
  panelScene: string;
  selectedDrawing: string | null;
  panelDrawing: string | null;
  layout: Block[];
  onPick: (sceneId: string, options?: Record<string, unknown>) => void;
  onSend: (sceneId: string, options: Record<string, unknown>) => void;
}> = ({ catalog, selectedScene, panelScene, selectedDrawing, panelDrawing, layout, onPick, onSend }) => {
  const { t } = useI18n();
  const categories = useMemo(() => Array.from(new Set(catalog.map((scene) => scene.category))), [catalog]);
  const initial = catalog.find((scene) => scene.id === selectedScene)?.category ?? categories[0];
  const [category, setCategory] = useState(initial);
  const active = categories.includes(category) ? category : categories[0];
  const shown = catalog.filter((scene) => scene.category === active);
  const rows: string[][] = [];
  for (let i = 0; i < categories.length; i += CHIPS_PER_ROW) rows.push(categories.slice(i, i + CHIPS_PER_ROW));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {rows.map((row) => (
        <Focusable key={row.join()} flow-children="row" style={{ display: "flex", gap: 6 }}>
          {row.map((id) => (
            <CategoryChip key={id} label={t(`accessories.category.${id}`)} selected={id === active} onPick={() => setCategory(id)} />
          ))}
        </Focusable>
      ))}
      {active === "custom" ? (
        <MyCreations selectedDrawing={selectedDrawing} panelDrawing={panelDrawing} composing={selectedScene === "composed"}
          composedOnPanel={panelScene === "composed"} layout={layout}
          onPick={(id) => onPick("custom", { drawing: id })}
          onSend={onSend} />
      ) : (
        <Focusable flow-children="grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
          {shown.map((scene) => (
            <SceneTile key={scene.id} scene={scene} selected={scene.id === selectedScene} onPanel={scene.id === panelScene}
              onPick={() => onPick(scene.id)} />
          ))}
        </Focusable>
      )}
    </div>
  );
};
