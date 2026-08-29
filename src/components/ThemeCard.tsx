import { Focusable } from "@decky/ui";
import { LuDownload, LuSparkles } from "react-icons/lu";
import { useRef } from "react";

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

function StatePill({ card }: { card: ThemeCardModel }) {
  const { t } = useI18n();
  const key = card.active
    ? "themes.state.active"
    : card.updateAvailable
      ? "themes.state.updateAvailable"
      : card.installed
        ? "themes.state.installed"
        : "themes.state.notInstalled";
  const color = card.active ? theme.color.ok : card.updateAvailable ? theme.color.warn : theme.color.textMuted;
  return (
    <span style={{ fontSize: theme.font.caption, color, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
      {card.installed ? <LuSparkles size={12} /> : <LuDownload size={12} />}
      {t(key)}
    </span>
  );
}

export function ThemeCard({ card, operation, onOpen }: Props) {
  const { t } = useI18n();
  const activating = useRef(false);
  const busy = operation !== null && operation.themeId === card.id;
  const activate = () => {
    if (busy || activating.current) return;
    activating.current = true;
    onOpen();
    window.setTimeout(() => { activating.current = false; }, 0);
  };
  return (
    <Focusable
      data-testid={`theme-card-${card.id}`}
      role="button"
      aria-label={card.catalog.name}
      onActivate={activate}
      onClick={activate}
      style={{
        display: "block",
        width: "100%",
        minWidth: 0,
        cursor: "pointer",
      }}
    >
      <div style={{ ...theme.card, padding: theme.space.sm, opacity: busy ? 0.62 : 1, overflow: "hidden" }}>
      <Preview id={card.id} />
      <div style={{ padding: `${theme.space.sm}px ${theme.space.xs}px ${theme.space.xs}px` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: theme.space.sm }}>
          <span style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 750, minWidth: 0, overflowWrap: "anywhere" }}>
            {card.catalog.name}
          </span>
          <StatePill card={card} />
        </div>
        <div style={{ marginTop: 5, color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.35 }}>
          {t(card.catalog.descriptionKey)}
        </div>
      </div>
      </div>
    </Focusable>
  );
}
