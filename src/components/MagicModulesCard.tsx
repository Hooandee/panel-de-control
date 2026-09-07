import { FC, useRef } from "react";
import { DialogButton, showModal } from "@decky/ui";
import { LuPuzzle } from "react-icons/lu";

import type {
  ControllerAction,
  ControllerActionResult,
  MagicModulesState,
} from "../api";
import { useI18n } from "../i18n";
import { canEject, moduleStateKey, outcomeKey } from "../mandos/magicModules";
import { theme } from "../theme";
import { ConfirmDialog } from "./ConfirmDialog";

interface Props {
  modules: MagicModulesState;
  pending: ControllerAction | null;
  result: ControllerActionResult | null;
  onAction: (action: ControllerAction) => void;
}

const ACTIONS: Array<{ action: ControllerAction; label: string }> = [
  { action: "eject_left", label: "mandos.modules.eject.left" },
  { action: "eject_right", label: "mandos.modules.eject.right" },
  { action: "eject_both", label: "mandos.modules.eject.both" },
];

export const MagicModulesCard: FC<Props> = ({ modules, pending, result, onAction }) => {
  const { t } = useI18n();
  const opening = useRef(false);

  const confirm = (action: ControllerAction) => {
    if (opening.current || !canEject(modules, action, pending)) return;
    opening.current = true;
    showModal(
      <ConfirmDialog
        title={t("mandos.modules.confirm.title")}
        desc={t("mandos.modules.confirm.desc")}
        confirmLabel={t("mandos.modules.confirm.ok")}
        cancelLabel={t("mandos.modules.confirm.cancel")}
        onConfirm={() => {
          opening.current = false;
          onAction(action);
        }}
        icon={<LuPuzzle size={18} color={theme.color.warn} />}
      />,
    );
    window.setTimeout(() => { opening.current = false; }, 0);
  };

  return (
    <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
        <LuPuzzle size={16} color={theme.color.accent} /> {t("mandos.modules.title")}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm, margin: `${theme.space.sm}px 0` }}>
        {(["left", "right"] as const).map((side) => (
          <div key={side} style={{ padding: theme.space.sm, borderRadius: theme.radius.sm, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t(`mandos.modules.${side}`)}</div>
            <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, fontWeight: 700, marginTop: 2 }}>
              {t(moduleStateKey(modules[side]))}
            </div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4, marginBottom: theme.space.sm }}>
        {t("mandos.modules.source.hhd")}
      </div>
      {!modules.supported && (
        <div role="status" style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginBottom: theme.space.sm }}>
          {t("mandos.modules.unavailable")}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.xs }}>
        {ACTIONS.map(({ action, label }, index) => (
          <DialogButton
            key={action}
            disabled={!canEject(modules, action, pending)}
            style={{ gridColumn: index === 2 ? "1 / -1" : undefined, width: "100%" }}
            onClick={() => confirm(action)}
          >
            {pending === action ? t("mandos.modules.running") : t(label)}
          </DialogButton>
        ))}
      </div>
      {result && (
        <div role="status" style={{ fontSize: theme.font.caption, color: result.outcome === "confirmed" ? theme.color.ok : theme.color.warn, lineHeight: 1.4, marginTop: theme.space.sm }}>
          {t(outcomeKey(result.outcome))}
        </div>
      )}
    </div>
  );
};
