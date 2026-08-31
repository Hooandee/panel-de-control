import { Focusable } from "@decky/ui";
import { LuDownload, LuLockKeyhole, LuSparkles } from "react-icons/lu";
import { type CSSProperties, useRef } from "react";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import type { ThemeCardModel } from "../themes/state";
import type { ThemesOperation } from "../themes/useThemes";

interface Props {
  card: ThemeCardModel;
  operation: ThemesOperation | null;
  onOpen(): void;
}

const previewStyle = {
  height: 78,
  position: "relative",
  overflow: "hidden",
  borderRadius: theme.radius.sm,
  background: "linear-gradient(135deg, #11131b 0%, #25142c 48%, #072b35 100%)",
} as const;

function Preview({ id }: { id: string }) {
  const obsidian = id === "hooandee-obsidian-bloom";
  const shattered = id === "hooandee-shattered-realms";
  const background = obsidian
    ? "radial-gradient(circle at 78% 18%, rgba(52,245,255,.72), transparent 20%), radial-gradient(circle at 27% 72%, rgba(255,43,177,.72), transparent 28%), #020204"
    : shattered
      ? "radial-gradient(circle at 72% 25%, rgba(255,177,74,.52), transparent 24%), linear-gradient(140deg, #151126, #372031 52%, #111520)"
      : "radial-gradient(circle at 72% 28%, rgba(124,224,160,.55), transparent 24%), linear-gradient(145deg, #101820, #183744)";
  return (
    <div style={{ ...previewStyle, background }}>
      {[0, 1, 2, 3].map((index) => (
        <div
          key={index}
          style={{
            position: "absolute",
            left: 14 + index * 46,
            top: 16 + (index % 2) * 7,
            width: 34,
            height: 48,
            borderRadius: 5,
            background: "linear-gradient(160deg, rgba(255,255,255,.3), rgba(255,255,255,.04))",
            boxShadow: obsidian && index === 2 ? "0 0 18px rgba(52,245,255,.65)" : "0 8px 16px rgba(0,0,0,.35)",
            transform: obsidian && index === 2 ? "translateY(-5px) scale(1.08)" : undefined,
          }}
        />
      ))}
    </div>
  );
}

function StatePill({ card, id }: { card: ThemeCardModel; id: string }) {
  const { t } = useI18n();
  let key = "themes.state.notInstalled";
  let color: string = theme.color.textMuted;
  let StateIcon = card.catalog.installSources.length > 0 ? LuDownload : LuLockKeyhole;
  if (card.catalog.availability === "coming-soon") {
    key = "themes.state.comingSoon";
    StateIcon = LuLockKeyhole;
  } else if (card.active) {
    key = "themes.state.active";
    color = theme.color.ok;
    StateIcon = LuSparkles;
  } else if (card.installed) {
    key = "themes.state.installed";
    StateIcon = LuSparkles;
  }
  return (
    <span id={id} style={{ fontSize: theme.font.caption, color, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
      <StateIcon size={12} aria-hidden />
      {t(key)}
    </span>
  );
}

export function ThemeCard({ card, operation, onOpen }: Props) {
  const { t } = useI18n();
  const activating = useRef(false);
  const comingSoon = card.catalog.availability === "coming-soon";
  const busy = operation !== null;
  const nameId = `theme-card-${card.id}-name`;
  const statusId = `theme-card-${card.id}-status`;
  const descriptionId = `theme-card-${card.id}-description`;
  const activate = () => {
    if (busy || activating.current) return;
    activating.current = true;
    queueMicrotask(() => { activating.current = false; });
    onOpen();
  };
  const contents = (
    <div style={{ ...theme.card, padding: theme.space.sm, opacity: busy || comingSoon ? 0.62 : 1, overflow: "hidden" }}>
      <Preview id={card.id} />
      <div style={{ padding: `${theme.space.sm}px ${theme.space.xs}px ${theme.space.xs}px` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: theme.space.sm }}>
          <span id={nameId} style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 750, minWidth: 0, overflowWrap: "anywhere" }}>
            {t(card.catalog.nameKey)}
          </span>
          <StatePill card={card} id={statusId} />
        </div>
        <div id={descriptionId} style={{ marginTop: 5, color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.35 }}>
          {t(card.catalog.descriptionKey)}
        </div>
        {(card.publishedVersion || card.updateAvailable) && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 5, color: theme.color.warn, fontSize: theme.font.caption, fontWeight: 700 }}>
            {card.publishedVersion && (
              <span>{t(
                card.publicationCompatibility === "compatible"
                  ? "themes.remote.card.available"
                  : "themes.remote.card.incompatible",
                { version: card.publishedVersion },
              )}</span>
            )}
            {card.updateAvailable && <span>{t("themes.state.updateAvailable")}</span>}
          </div>
        )}
      </div>
    </div>
  );

  if (comingSoon) {
    return (
      <div
        data-testid={`theme-card-${card.id}`}
        role="group"
        aria-labelledby={`${nameId} ${statusId}`}
        aria-describedby={descriptionId}
        aria-disabled="true"
        style={{ display: "block", width: "100%", minWidth: 0 }}
      >
        {contents}
      </div>
    );
  }

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
      {contents}
    </Focusable>
  );
}
