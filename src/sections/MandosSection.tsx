import { FC, useEffect, useState } from "react";
import { DialogButton, Dropdown, PanelSectionRow } from "@decky/ui";
import { LuGamepad2, LuRotateCcw } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import {
  getControllerConfig,
  resetController,
  setControllerButton,
  setControllerSetting,
  type ControllerConfig,
} from "../api";
import {
  currentTargetValue,
  managerDescKey,
  managerLabelKey,
  prettyTarget,
  valueToTarget,
} from "../mandos/logic";
import { Loading } from "../components/Loading";

/** Raised card chrome with a titled header row. */
const Card: FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden" }}>
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: theme.space.xs,
        fontSize: theme.font.body,
        fontWeight: 700,
        color: theme.color.textPrimary,
        marginBottom: theme.space.sm,
      }}
    >
      <LuGamepad2 size={16} color={theme.color.accent} /> {title}
    </div>
    {children}
  </div>
);

/** A labelled control: a small muted caption above a full-width control. Vertical
 *  so the dropdown never fights the label for width in the narrow QAM (the old
 *  side-by-side layout overflowed the card). */
const Row: FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, padding: `${theme.space.xs}px 0` }}>
    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, letterSpacing: 0.2 }}>
      {label}
    </span>
    <div style={{ width: "100%", overflow: "hidden" }}>{children}</div>
  </div>
);

/** A remap entry: the physical button's silkscreen legend (Y1/M1…) as a keycap
 *  chip beside its target selector. Silkscreen names are short, so a horizontal
 *  keycap + dropdown reads like a controller legend and matches the plugin's pill
 *  aesthetic — nicer than a plain full-width dropdown row. */
const RemapRow: FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: theme.space.sm,
      padding: theme.space.xs,
      marginBottom: theme.space.xs,
      borderRadius: theme.radius.sm,
      boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    }}
  >
    <span
      style={{
        flex: "0 0 auto",
        minWidth: 38,
        height: 30,
        padding: `0 ${theme.space.sm}px`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: theme.radius.sm,
        background: theme.color.accent,
        color: theme.color.onAccent,
        fontWeight: 700,
        fontSize: theme.font.body,
        letterSpacing: 0.5,
        boxShadow: "0 1px 2px rgba(0,0,0,0.4)",
      }}
    >
      {label}
    </span>
    <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>{children}</div>
  </div>
);

/**
 * Mandos — controller manager hub.
 *
 * Cooperates with whichever daemon owns the gamepad (Handheld Daemon on Bazzite,
 * InputPlumber on SteamOS) — we never grab evdev ourselves. On InputPlumber we
 * offer a real per-button remap editor; on HHD we expose its controller settings
 * (mode + paddle behavior), since HHD delegates fine per-game remap to Steam
 * Input. When no manager is present we say so honestly.
 */
export const MandosSection: FC = () => {
  const { t } = useI18n();
  const [config, setConfig] = useState<ControllerConfig | null>(null);

  useEffect(() => {
    getControllerConfig().then(setConfig).catch(() => {});
  }, []);

  if (!config) return <Loading />;

  const manager = config.manager;
  const version = config.manager_version;

  const onSetButton = (source: string, value: string) =>
    // Empty value = the "Default" option → send no targets so the backend reverts
    // this one button to the device default.
    setControllerButton(source, value ? [valueToTarget(value)] : []).then(setConfig).catch(() => {});
  const onSetSetting = (field: string, value: string) =>
    setControllerSetting(field, value).then(setConfig).catch(() => {});
  const onReset = () => resetController().then(setConfig).catch(() => {});

  // Dropdown options: a "Default" entry (empty value → backend reverts that one
  // button to the device default) plus grouped buttons + keys.
  const targetGroups = [
    { data: "", label: t("mandos.remap.default") },
    {
      label: t("mandos.targets.buttons"),
      options: (config.gamepad_targets ?? []).map((g) => ({
        data: `gp:${g}`,
        label: prettyTarget(`gp:${g}`),
      })),
    },
    {
      label: t("mandos.targets.keys"),
      options: (config.key_targets ?? []).map((k) => ({
        data: `key:${k}`,
        label: prettyTarget(`key:${k}`),
      })),
    },
  ];

  const label = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };

  // Remappable physical buttons (empty for non-remap configs / unvalidated devices).
  const buttons = config.buttons ?? [];

  return (
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.section }}>
        {/* Manager status — honest, reads the live system. */}
        <Card title={t("mandos.title")}>
          <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs }}>
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {t("mandos.manager.label")}
            </span>
            <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
              {t(managerLabelKey(manager))}
            </span>
            {version && (
              <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>v{version}</span>
            )}
          </div>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs, lineHeight: 1.4 }}>
            {t(managerDescKey(manager))}
          </div>
        </Card>

        {/* InputPlumber: real per-button remap editor. */}
        {config.kind === "remap" && (
          <Card title={t("mandos.remap.title")}>
            {buttons.map((b) => (
              // b.label is the literal silkscreen name (Y1/M2/…) — render as-is.
              <RemapRow key={b.source} label={b.label}>
                <Dropdown
                  rgOptions={targetGroups}
                  selectedOption={currentTargetValue(b.target ?? [])}
                  strDefaultLabel={t("mandos.remap.default")}
                  onChange={(o) => onSetButton(b.source, o.data as string)}
                />
              </RemapRow>
            ))}
            {/* Honest footnote: no buttons → why (unvalidated model vs a transient
                empty-caps read, distinguished by device_known); otherwise the
                global-scope reminder. */}
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: `${theme.space.sm}px 0`, lineHeight: 1.4 }}>
              {buttons.length === 0
                ? t(config.device_known === false ? "mandos.remap.uncalibrated" : "mandos.remap.nobuttons")
                : t("mandos.remap.note")}
            </div>
            <DialogButton
              style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs }}
              onClick={onReset}
            >
              <LuRotateCcw size={14} /> {t("mandos.remap.reset")}
            </DialogButton>
          </Card>
        )}

        {/* HHD: controller settings (fine per-game remap goes to Steam Input). */}
        {config.kind === "settings" && (
          <Card title={t("mandos.settings.title")}>
            <Row label={t("mandos.mode.label")}>
              <Dropdown
                rgOptions={(config.mode_options ?? []).map((m) => ({
                  data: m,
                  label: label(`mandos.mode.${m}`, m),
                }))}
                selectedOption={config.mode ?? undefined}
                onChange={(o) => onSetSetting("mode", o.data as string)}
              />
            </Row>
            {config.paddles_as != null && (
              <Row label={t("mandos.paddles.label")}>
                <Dropdown
                  rgOptions={(config.paddles_options ?? []).map((p) => ({
                    data: p,
                    label: label(`mandos.paddles.${p}`, p),
                  }))}
                  selectedOption={config.paddles_as ?? undefined}
                  onChange={(o) => onSetSetting("paddles_as", o.data as string)}
                />
              </Row>
            )}
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.sm, lineHeight: 1.4 }}>
              {t("mandos.settings.note")}
            </div>
          </Card>
        )}
      </div>
    </PanelSectionRow>
  );
};
