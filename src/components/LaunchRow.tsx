import { FC } from "react";
import { Focusable, TextField } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ValuePills } from "./LaunchPills";
import { LaunchEditor } from "../launch/useLaunchEditor";
import { LaunchTools, Pill, isPillAvailable } from "../launch/catalog";

/** A round on/off switch matching the section's visual language. */
const RowSwitch: FC<{ active: boolean; disabled?: boolean; onToggle: () => void }> = ({ active, disabled, onToggle }) => {
  const track = disabled ? "rgba(255,255,255,0.12)" : active ? theme.color.accent : "rgba(255,255,255,0.14)";
  const knob = active && !disabled ? theme.color.onAccent : "rgba(255,255,255,0.55)";
  const body = (
    <div style={{ width: 38, height: 22, borderRadius: 20, background: track, position: "relative", flexShrink: 0 }}>
      <div style={{ position: "absolute", top: 2, [active ? "right" : "left"]: 2, width: 18, height: 18, borderRadius: "50%", background: knob }} />
    </div>
  );
  if (disabled) return body;
  return (
    <Focusable style={{ cursor: "pointer" }} onActivate={onToggle} onClick={onToggle}>
      {body}
    </Focusable>
  );
};

/**
 * One launch-option as a row: title (+ the real flag, small) and a plain-language
 * description, with its control. Toggles get a switch on the right; value pills a
 * chip row below; free-text pills a text field. An unavailable pill (tool not
 * installed) is dimmed with an honest badge and its control disabled.
 */
export const LaunchRow: FC<{ pill: Pill; ed: LaunchEditor; tools: LaunchTools; caveat?: string }> = ({ pill, ed, tools, caveat }) => {
  const { t } = useI18n();
  const available = isPillAvailable(pill, tools);
  const sel = ed.selections[pill.id];
  const isValue = !!pill.options;
  const isText = !!pill.freeText;
  const isToggle = !isValue && !isText;

  return (
    <div style={{ ...theme.card, padding: `10px 11px`, marginBottom: theme.space.sm, opacity: available ? 1 : 0.55 }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.md }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: theme.font.body, fontWeight: 500, color: theme.color.textPrimary, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            {t(pill.labelKey)}
            {pill.raw && <span style={{ fontFamily: "monospace", fontSize: 10, color: theme.color.textMuted }}>{pill.raw}</span>}
            {!available && (
              <span style={{ fontSize: 9, color: theme.color.textMuted, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`, borderRadius: 10, padding: "1px 6px" }}>
                {t("params.notInstalled")}
              </span>
            )}
          </div>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>{t(pill.descKey)}</div>
        </div>
        {isToggle && (
          <RowSwitch active={!!sel} disabled={!available} onToggle={() => ed.set(pill.id, !sel)} />
        )}
      </div>

      {isValue && pill.options && (
        <div style={{ marginTop: theme.space.sm }}>
          <ValuePills
            offLabel={t("params.off")}
            options={pill.options.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
            current={(sel as string | undefined) ?? null}
            onSelect={(v) => ed.set(pill.id, v)}
          />
        </div>
      )}

      {isText && (
        <div style={{ marginTop: theme.space.sm }}>
          <TextField
            value={typeof sel === "string" ? sel : ""}
            onChange={(e) => ed.set(pill.id, e.target.value || null)}
            // @ts-expect-error Decky TextField forwards input attrs; placeholder is valid.
            placeholder={pill.placeholderKey ? t(pill.placeholderKey) : ""}
          />
        </div>
      )}

      {caveat && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.warn, display: "flex", gap: 6, alignItems: "flex-start", marginTop: theme.space.xs }}>
          <span>{caveat}</span>
        </div>
      )}
    </div>
  );
};
