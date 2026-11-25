import { Focusable } from "@decky/ui";
import { FC, useEffect, useMemo, useState } from "react";

import type { AccessorySceneMeta } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import type { Block } from "./ComposerEditor";
import { Chip, ChipRow } from "./EditorShell";
import { MyCreations } from "./MyCreations";
import { DecodedFrames } from "./pixelFrames";
import { PixelPreview } from "./PixelPreview";
import { loadPreview, setGalleryCategory, useSceneDraft } from "./useAccessories";
import { OnPanelDot, TileRows, tileStyle } from "./tiles";

const TILE_PITCH = 1.75;
const CATEGORIES_PER_ROW = 3;
const chunk = <T,>(list: T[], size: number): T[][] =>
  Array.from({ length: Math.ceil(list.length / size) }, (_, i) => list.slice(i * size, i * size + size));

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

export const SceneGallery: FC<{
  catalog: AccessorySceneMeta[];
  selectedScene: string;
  panelScene: string;
  selectedDrawing: string | null;
  panelDrawing: string | null;
  layout: Block[];
  onPick: (sceneId: string, options?: Record<string, unknown>) => void;
  onSend: (sceneId: string, options: Record<string, unknown>) => void;
  children?: React.ReactNode;
}> = ({ catalog, selectedScene, panelScene, selectedDrawing, panelDrawing, layout, onPick, onSend, children }) => {
  const { t } = useI18n();
  const categories = useMemo(() => Array.from(new Set(catalog.map((scene) => scene.category))), [catalog]);
  const remembered = useSceneDraft().category;
  const category = remembered ?? catalog.find((scene) => scene.id === selectedScene)?.category ?? categories[0];
  const setCategory = setGalleryCategory;
  const active = categories.includes(category) ? category : categories[0];
  const shown = catalog.filter((scene) => scene.category === active);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {/* Equal rows of three: a scrolling strip hid the last categories at the menu's edge. */}
      <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        {chunk(categories, CATEGORIES_PER_ROW).map((row) => (
          <ChipRow key={row[0]}>
            {row.map((id) => (
              <Chip key={id} label={t(`accessories.category.${id}`)} active={id === active} onPick={() => setCategory(id)} />
            ))}
            {row.length < CATEGORIES_PER_ROW && <div style={{ flex: CATEGORIES_PER_ROW - row.length }} />}
          </ChipRow>
        ))}
      </Focusable>
      {active === "custom" ? (
        <MyCreations selectedDrawing={selectedDrawing} panelDrawing={panelDrawing} composing={selectedScene === "composed"}
          composedOnPanel={panelScene === "composed"} layout={layout}
          onPick={(id) => onPick("custom", { drawing: id })}
          onSend={onSend} />
      ) : (
        <TileRows>
          {shown.map((scene) => (
            <SceneTile key={scene.id} scene={scene} selected={scene.id === selectedScene} onPanel={scene.id === panelScene}
              onPick={() => onPick(scene.id)} />
          ))}
        </TileRows>
      )}
      {children}
    </div>
  );
};
