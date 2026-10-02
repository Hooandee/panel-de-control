import { FC, useEffect, useState } from "react";
import { ToggleField } from "@decky/ui";

import { getKioskState } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useViews } from "../customize/viewStore";
import { setKioskViewChosen, useKioskViewIds } from "../customize/kioskViewStore";
import { viewIconNode } from "../customize/viewIcons";

export const KioskViewsSetting: FC = () => {
  const { t } = useI18n();
  const [supported, setSupported] = useState(false);
  const views = useViews();
  const chosen = useKioskViewIds();

  useEffect(() => {
    let alive = true;
    getKioskState().then((state) => alive && setSupported(state.supported)).catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  if (!supported) return null;
  const withBlocks = views.filter((view) => view.blocks.length > 0);

  return (
    <>
      <div style={theme.sectionLabel}>{t("customize.kiosk.title")}</div>
      <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {withBlocks.length === 0 ? t("customize.kiosk.none") : t("customize.kiosk.hint")}
        </span>
        {withBlocks.map((view) => (
          <ToggleField
            key={view.id}
            icon={viewIconNode(view.icon)}
            label={view.name || t("customize.views.namePlaceholder")}
            checked={chosen.includes(view.id)}
            onChange={() => setKioskViewChosen(view.id)}
            bottomSeparator="none"
          />
        ))}
      </div>
    </>
  );
};
