import { FC, ReactNode, useRef } from "react";
import { Focusable, PanelSectionRow, showModal } from "@decky/ui";
import { LuLightbulb, LuStore } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ConfirmDialog } from "./ConfirmDialog";
import type { ColoresCardState } from "../system/colores";

interface Props {
  state: ColoresCardState;
  onInstall: () => void;
  onOpen: () => void;
  onOpenStore: () => void;
}

const actionFrameStyle = {
  width: "100%",
  minWidth: 0,
  borderRadius: theme.radius.sm,
  boxSizing: "border-box",
} as const;

const actionSurfaceStyle = {
  width: "100%",
  minWidth: 0,
  minHeight: 44,
  padding: `${theme.space.md}px ${theme.space.lg}px`,
  borderRadius: theme.radius.sm,
  boxSizing: "border-box",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: theme.space.xs,
  background: "rgba(255,255,255,0.08)",
  boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
  color: theme.color.textPrimary,
  fontSize: theme.font.body,
  fontWeight: 650,
} as const;

const RgbAction: FC<{ label: string; onTap?: () => void; children: ReactNode }> = ({ label, onTap, children }) => {
  const activating = useRef(false);
  const surface = (
    <div data-testid="system-rgb-action-surface" style={{ ...actionSurfaceStyle, opacity: onTap ? 1 : 0.5 }}>
      {children}
    </div>
  );
  if (!onTap) return <div style={actionFrameStyle}>{surface}</div>;
  const activate = () => {
    if (activating.current) return;
    activating.current = true;
    onTap();
    window.setTimeout(() => { activating.current = false; }, 0);
  };
  return (
    <Focusable
      data-testid="system-rgb-action"
      role="button"
      aria-label={label}
      onActivate={activate}
      onClick={activate}
      style={{ ...actionFrameStyle, cursor: "pointer" }}
    >
      {surface}
    </Focusable>
  );
};

/**
 * RGB-lighting integration card (Sistema). Bridges to the sibling Colores plugin:
 * opens its panel if installed, or installs it from its GitHub release (with a
 * confirm). Never rendered on Steam Deck (no RGB LEDs) — the section gates on
 * `hasRgb`; a "hidden" state here is just a defensive guard.
 */
export const ColoresCard: FC<Props> = ({ state, onInstall, onOpen, onOpenStore }) => {
  const { t } = useI18n();
  if (state === "hidden") return null;

  const installed = state === "open";
  const desc = installed ? t("system.rgb.desc.installed") : t("system.rgb.desc.install");

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: theme.space.xs,
            fontSize: theme.font.body,
            fontWeight: 700,
            color: theme.color.textPrimary,
          }}
        >
          <LuLightbulb size={16} color={theme.color.accent} /> {t("system.rgb.title")}
        </div>
        <div
          style={{
            fontSize: theme.font.caption,
            color: state === "error" ? theme.color.warn : theme.color.textMuted,
            margin: `${theme.space.xs}px 0 ${theme.space.md}px`,
            lineHeight: 1.4,
          }}
        >
          {state === "error" ? t("system.rgb.error") : desc}
        </div>

        {state === "open" && (
          <RgbAction label={t("system.rgb.open")} onTap={onOpen}>
            {t("system.rgb.open")}
          </RgbAction>
        )}

        {state === "install" && (
          <RgbAction
            label={t("system.rgb.install")}
            onTap={() =>
              showModal(
                <ConfirmDialog
                  title={t("system.rgb.confirm.title")}
                  desc={t("system.rgb.confirm.desc")}
                  confirmLabel={t("system.rgb.confirm.ok")}
                  cancelLabel={t("system.rgb.confirm.cancel")}
                  onConfirm={onInstall}
                />,
              )
            }
          >
            {t("system.rgb.install")}
          </RgbAction>
        )}

        {state === "installing" && (
          <RgbAction label={t("system.rgb.installing")}>
            {t("system.rgb.installing")}
          </RgbAction>
        )}

        {state === "error" && (
          <RgbAction label={t("system.rgb.store")} onTap={onOpenStore}>
            <LuStore size={14} /> {t("system.rgb.store")}
          </RgbAction>
        )}
      </div>
    </PanelSectionRow>
  );
};
