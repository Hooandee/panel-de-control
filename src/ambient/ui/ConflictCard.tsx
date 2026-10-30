import type { FC } from "react";
import { LuImage, LuMusic } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { Conflict } from "../core/arbiter";
import { Button, CardTitle, cardStyle } from "./primitives";

interface Props {
  conflict: Conflict;
  currentUrl: string | null;
  onChoose: (owner: "panel" | "theme" | "other") => void;
}

const Option: FC<{ label: string; image?: string | null; selected?: boolean }> = ({ label, image, selected }) => (
  <div style={{ borderRadius: theme.radius.sm, overflow: "hidden", background: "rgba(255,255,255,0.04)", boxShadow: selected ? `0 0 0 2px ${theme.color.accent}` : `inset 0 0 0 1px ${theme.color.hairline}` }}>
    <div style={{ aspectRatio: "16 / 10", background: image ? `center / cover no-repeat url("${image}")` : "linear-gradient(135deg,#231b3a,#3a2350 60%,#15111f)" }} />
    <div style={{ fontSize: theme.font.caption, padding: "6px 8px", color: selected ? theme.color.textPrimary : theme.color.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</div>
  </div>
);

export const ConflictCard: FC<Props> = ({ conflict, currentUrl, onChoose }) => {
  const { t } = useI18n();
  const accent = theme.color.accentRgb;
  const style = { ...cardStyle, background: `linear-gradient(180deg, rgba(${accent},0.10), rgba(${accent},0.03))`, boxShadow: `inset 0 0 0 1px rgba(${accent},0.35)` };

  if (conflict.kind === "music") {
    return (
      <div style={style}>
        <CardTitle wrap icon={<LuMusic size={15} />} title={t("ambient.conflict.music.title")} />
        <div style={{ fontSize: 12, color: theme.color.textMuted, lineHeight: 1.45 }}>{t("ambient.conflict.music.body")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
          <Button primary label={t("ambient.conflict.useMineMusic")} onActivate={() => onChoose("panel")} />
          <Button label={t("ambient.conflict.useTheirs")} onActivate={() => onChoose("other")} />
        </div>
      </div>
    );
  }

  const isTheme = conflict.kind === "theme";
  const name = conflict.name ?? "";
  if (!isTheme) {
    return (
      <div style={{ ...style, flexDirection: "row", alignItems: "center", gap: theme.space.sm, padding: `${theme.space.sm}px ${theme.space.md}px` }}>
        <LuImage size={15} style={{ color: theme.color.accent, flexShrink: 0 }} />
        <span style={{ flex: 1, minWidth: 0, fontSize: 12, lineHeight: 1.3, color: theme.color.textPrimary }}>{t("ambient.conflict.other.short")}</span>
        <Button primary label={t("ambient.conflict.keepMine.short")} onActivate={() => onChoose("panel")} style={{ height: 30, padding: "0 10px", fontSize: 12 }} />
        <Button label={t("ambient.conflict.letIt")} onActivate={() => onChoose("other")} style={{ height: 30, padding: "0 10px", fontSize: 12 }} />
      </div>
    );
  }
  return (
    <div style={style}>
      <CardTitle wrap icon={<LuImage size={15} />} title={isTheme ? t("ambient.conflict.theme.title", { name }) : t("ambient.conflict.other.title")} />
      <div style={{ fontSize: 12, color: theme.color.textMuted, lineHeight: 1.45 }}>{isTheme ? t("ambient.conflict.theme.body") : t("ambient.conflict.other.body")}</div>
      {isTheme && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
          <Option label={t("ambient.conflict.yours")} image={currentUrl} selected />
          <Option label={t("ambient.conflict.theirs", { name })} />
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
        <Button primary label={isTheme ? t("ambient.conflict.useMine") : t("ambient.conflict.keepMine")} onActivate={() => onChoose("panel")} />
        <Button label={isTheme ? t("ambient.conflict.useTheme") : t("ambient.conflict.letIt")} onActivate={() => onChoose(isTheme ? "theme" : "other")} />
      </div>
    </div>
  );
};
