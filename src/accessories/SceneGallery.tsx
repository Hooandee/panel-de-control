import { Focusable } from "@decky/ui";
import { FC, useEffect, useMemo, useState } from "react";

import type { AccessorySceneMeta } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { DecodedFrames } from "./pixelFrames";
import { PixelPreview } from "./PixelPreview";
import { loadPreview } from "./useAccessories";
import { MyCreations } from "./MyCreations";
import type { Block } from "./ComposerModal";

const TILE_PITCH = 1.75;

const SceneTile: FC<{ scene: AccessorySceneMeta; active: boolean; onChoose: () => void }> = ({ scene, active, onChoose }) => {
  const { t } = useI18n();
  const [decoded, setDecoded] = useState<DecodedFrames | null>(null);
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    let live = true;
    void loadPreview(scene.id).then((value) => { if (live) setDecoded(value); });
    return () => { live = false; };
  }, [scene.id]);
  const ring = focused
    ? `inset 0 0 0 1px ${theme.color.accent}, 0 0 0 2px ${theme.color.accent}`
    : active ? `inset 0 0 0 1px ${theme.color.accent}88` : `inset 0 0 0 1px ${theme.color.outline}`;
  return (
    <Focusable
      onActivate={onChoose}
      onClick={onChoose}
      onGamepadFocus={() => setFocused(true)}
      onGamepadBlur={() => setFocused(false)}
      style={{
        borderRadius: theme.radius.md,
        background: active ? `rgba(${theme.color.accentRgb},0.10)` : theme.color.surfaceRaised,
        boxShadow: ring,
        padding: theme.space.sm,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: theme.space.xs + 2,
        transition: "box-shadow 120ms ease, transform 120ms ease, background 160ms ease",
        transform: focused ? "scale(1.03)" : "scale(1)",
        minWidth: 0,
      }}
    >
      <PixelPreview decoded={decoded} pitch={TILE_PITCH} animate={focused || active} label={t(scene.labelKey)} />
      <div style={{ display: "flex", alignItems: "center", gap: 5, width: "100%", justifyContent: "center", minWidth: 0 }}>
        {active && <span style={{ width: 6, height: 6, borderRadius: 3, background: theme.color.accent, flex: "0 0 auto",
          boxShadow: `0 0 6px ${theme.color.accent}` }} />}
        <span style={{ fontSize: theme.font.caption, fontWeight: 650, color: active ? theme.color.textPrimary : theme.color.textMuted,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t(scene.labelKey)}</span>
      </div>
    </Focusable>
  );
};

export const SceneGallery: FC<{
  catalog: AccessorySceneMeta[];
  activeScene: string;
  onChoose: (sceneId: string, options?: Record<string, unknown>) => void;
  activeDrawing: string | null;
  layout: Block[];
}> = ({ catalog, activeScene, onChoose, activeDrawing, layout }) => {
  const { t } = useI18n();
  const categories = useMemo(() => Array.from(new Set(catalog.map((scene) => scene.category))), [catalog]);
  const activeCategory = catalog.find((scene) => scene.id === activeScene)?.category ?? categories[0];
  const [category, setCategory] = useState(activeCategory);
  const shown = catalog.filter((scene) => scene.category === (categories.includes(category) ? category : categories[0]));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {categories.length > 1 && (
        <Focusable flow-children="row" style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 2 }}>
          {categories.map((id) => {
            const selected = id === category;
            return (
              <Focusable key={id} onActivate={() => setCategory(id)} onClick={() => setCategory(id)}
                style={{ flex: "0 0 auto", padding: "5px 11px", borderRadius: 999, fontSize: theme.font.caption, fontWeight: 650,
                  background: selected ? theme.color.selectedFill : "rgba(255,255,255,0.06)",
                  color: selected ? theme.color.onAccent : theme.color.textMuted }}>
                {t(`accessories.category.${id}`)}
              </Focusable>
            );
          })}
        </Focusable>
      )}
      {(categories.includes(category) ? category : categories[0]) === "custom" ? (
        <MyCreations activeDrawing={activeScene === "custom" ? activeDrawing : null}
          composing={activeScene === "composed"} layout={layout}
          onShow={(id) => onChoose("custom", { drawing: id })}
          onCompose={(blocks) => onChoose("composed", { layout: { blocks } })} />
      ) : (
      <Focusable flow-children="grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
        {shown.map((scene) => (
          <SceneTile key={scene.id} scene={scene} active={scene.id === activeScene} onChoose={() => onChoose(scene.id)} />
        ))}
      </Focusable>
      )}
    </div>
  );
};
