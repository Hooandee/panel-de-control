import { Focusable } from "@decky/ui";
import { type CSSProperties, useRef } from "react";
import { LuDownload, LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { localizePublishedText } from "../themes/remotePublication";
import type { ThemeCardModel } from "../themes/state";
import type { ThemesOperation } from "../themes/useThemes";

interface Props {
  card: ThemeCardModel;
  operation: ThemesOperation | null;
  onOpen(): void;
}

const PREVIEW_STYLE: CSSProperties = {
  height: 78,
  position: "relative",
  overflow: "hidden",
  borderRadius: theme.radius.sm,
  background: `linear-gradient(145deg, ${theme.color.surfaceRaised}, ${theme.color.surface})`,
  boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
};

const PREVIEW_LAYERS = [
  { left: "9%", top: 12, width: "19%", height: 52 },
  { left: "32%", top: 20, width: "19%", height: 44 },
  { left: "55%", top: 9, width: "19%", height: 55 },
] as const;

function NeutralPreview() {
  return (
    <div data-testid="theme-preview" aria-hidden style={PREVIEW_STYLE}>
      <div style={{ position: "absolute", inset: 10, borderRadius: 8, background: theme.color.surface }} />
      {PREVIEW_LAYERS.map((layer) => (
        <div
          key={layer.left}
          style={{
            position: "absolute",
            ...layer,
            borderRadius: 5,
            background: `linear-gradient(160deg, rgba(${theme.color.accentRgb}, 0.34), ${theme.color.surfaceRaised})`,
            boxShadow: "0 5px 14px rgba(0,0,0,0.35)",
          }}
        />
      ))}
      <div style={{ position: "absolute", right: "8%", top: 15, width: "12%", height: 4, borderRadius: 4, background: theme.color.accent }} />
    </div>
  );
}

function StatePill({ card, id }: { card: ThemeCardModel; id: string }) {
  const { t } = useI18n();
  const active = card.active;
  const installed = card.installed;
  const StateIcon = active || installed ? LuSparkles : LuDownload;
  const label = active
    ? "themes.state.active"
    : installed
      ? "themes.state.installed"
      : "themes.state.notInstalled";
  return (
    <span id={id} style={{ fontSize: theme.font.caption, color: active ? theme.color.ok : theme.color.textMuted, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
      <StateIcon size={12} aria-hidden /> {t(label)}
    </span>
  );
}

export function ThemeCard({ card, operation, onOpen }: Props) {
  const { lang, t } = useI18n();
  const activating = useRef(false);
  const busy = operation !== null;
  const name = localizePublishedText(card.release.displayName, lang);
  const description = localizePublishedText(card.release.description, lang);
  const nameId = `theme-card-${card.id}-name`;
  const statusId = `theme-card-${card.id}-status`;
  const descriptionId = `theme-card-${card.id}-description`;
  const activate = () => {
    if (busy || activating.current) return;
    activating.current = true;
    queueMicrotask(() => { activating.current = false; });
    onOpen();
  };
  return (
    <Focusable
      data-testid={`theme-card-${card.id}`}
      data-pdc-focus-radius="true"
      role="button"
      aria-labelledby={`${nameId} ${statusId}`}
      aria-describedby={descriptionId}
      aria-disabled={busy}
      onActivate={activate}
      onClick={activate}
      style={{
        display: "block",
        width: "100%",
        minWidth: 0,
        cursor: busy ? "default" : "pointer",
        "--pdc-focus-radius": `${theme.radius.md}px`,
      } as CSSProperties}
    >
      <div style={{ ...theme.card, padding: theme.space.sm, opacity: busy ? 0.62 : 1, overflow: "hidden" }}>
        <NeutralPreview />
        <div style={{ padding: `${theme.space.sm}px ${theme.space.xs}px ${theme.space.xs}px` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: theme.space.sm }}>
            <span id={nameId} style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 750, minWidth: 0, overflowWrap: "anywhere" }}>
              {name}
            </span>
            <StatePill card={card} id={statusId} />
          </div>
          <div id={descriptionId} style={{ marginTop: 5, color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.35 }}>
            {description}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 5, color: card.installable ? theme.color.accent : theme.color.warn, fontSize: theme.font.caption, fontWeight: 700 }}>
            <span>{t(card.installable ? "themes.remote.card.available" : "themes.remote.card.incompatible", { version: card.release.publishedVersion })}</span>
            {card.updateAvailable ? <span>{t("themes.state.updateAvailable")}</span> : null}
          </div>
        </div>
      </div>
    </Focusable>
  );
}
