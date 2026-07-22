import { FC } from "react";
import { ModalRoot, showModal, Focusable, DialogButton } from "@decky/ui";
import { LuPower, LuEyeOff } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";

interface Opts {
  moduleName: string;
  onDisable: () => void;
  /** When set, offer "hide here instead" — for a module that has a placement to
   *  hide (a tab or block). Omitted for placeless modules (e.g. learning). */
  onHideInstead?: () => void;
}

const Body: FC<Opts & { closeModal?: () => void }> = ({ moduleName, onDisable, onHideInstead, closeModal }) => {
  const { t } = useI18n();
  const close = () => closeModal?.();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, maxWidth: 420, margin: "0 auto", padding: theme.space.lg }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.xs }}>
        <div style={{ width: 56, height: 56, borderRadius: theme.radius.md, background: theme.color.surfaceRaised, display: "grid", placeItems: "center", boxShadow: `inset 0 0 0 1px ${theme.color.warn}` }}>
          <LuPower size={26} color={theme.color.warn} />
        </div>
        <div style={{ fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary, textAlign: "center" }}>
          {t("customize.disable.title", { name: moduleName })}
        </div>
      </div>

      <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.45, textAlign: "center" }}>
        {t("customize.disable.body")}
      </div>

      {onHideInstead && (
        <div style={{ display: "flex", gap: theme.space.sm, alignItems: "flex-start", padding: theme.space.md, borderRadius: theme.radius.sm, background: `rgba(${theme.color.accentRgb},0.06)`, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
          <LuEyeOff size={16} color={theme.color.accent} style={{ flex: "0 0 auto", marginTop: 1 }} />
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>
            {t("customize.disable.hint")}
          </div>
        </div>
      )}

      <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <DialogButton onClick={() => { onDisable(); close(); }}>
          {t("customize.disable")}
        </DialogButton>
        {onHideInstead && (
          <DialogButton onClick={() => { onHideInstead(); close(); }}>
            {t("customize.disable.hide")}
          </DialogButton>
        )}
        <DialogButton onClick={close}>
          {t("customize.disable.cancel")}
        </DialogButton>
      </Focusable>
    </div>
  );
};

const DisableModuleModalRoot: FC<Opts & { closeModal?: () => void }> = (p) => (
  <ModalRoot closeModal={p.closeModal} bAllowFullSize>
    <FocusRoot>
      <Body {...p} />
    </FocusRoot>
  </ModalRoot>
);

/** Warn that disabling a module is GLOBAL (stops it across the whole panel), and
 *  offer to hide it here instead when it has a placement to hide. */
export function openDisableModuleModal(opts: Opts): void {
  showModal(<DisableModuleModalRoot {...opts} />, window);
}
