import { FC, ReactNode } from "react";
import { DialogButton, Dropdown } from "@decky/ui";
import { LuGamepad2, LuRotateCcw } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import {
  currentTargetValue,
  managerDescKey,
  managerLabelKey,
  prettyTarget,
} from "../mandos/logic";
import { useMandos } from "../mandos/mandosContext";
import { ProfileSelector } from "../components/ProfileSelector";
import { registerBlock } from "../customize/blocks";

/** Raised card chrome with a titled header row. */
const Card: FC<{ title: string; children: ReactNode }> = ({ title, children }) => (
  <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden" }}>
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary, marginBottom: theme.space.sm }}>
      <LuGamepad2 size={16} color={theme.color.accent} /> {title}
    </div>
    {children}
  </div>
);

/** A labelled control: a small muted caption above a full-width control. Vertical
 *  so the dropdown never fights the label for width in the narrow QAM. */
const Row: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, padding: `${theme.space.xs}px 0` }}>
    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, letterSpacing: 0.2 }}>{label}</span>
    <div style={{ width: "100%", overflow: "hidden" }}>{children}</div>
  </div>
);

/** A remap entry: the physical button's silkscreen legend (Y1/M1…) as a keycap
 *  chip beside its target selector. */
const RemapRow: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, padding: theme.space.xs, marginBottom: theme.space.xs, borderRadius: theme.radius.sm, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
    <span style={{ flex: "0 0 auto", minWidth: 38, height: 30, padding: `0 ${theme.space.sm}px`, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: theme.radius.sm, background: theme.color.accent, color: theme.color.onAccent, fontWeight: 700, fontSize: theme.font.body, letterSpacing: 0.5, boxShadow: "0 1px 2px rgba(0,0,0,0.4)" }}>
      {label}
    </span>
    <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>{children}</div>
  </div>
);

// Mandos blocks. All read the shared MandosProvider (one controller config + scope
// owned by the section). Availability of remap/settings is state-derived from the
// live config's kind (InputPlumber → remap, HHD → settings); manager is always shown.

const ManagerBlock: FC = () => {
  const { t } = useI18n();
  const { config } = useMandos();
  if (!config) return null;
  const manager = config.manager;
  const version = config.manager_version;
  return (
    <Card title={t("mandos.title")}>
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs }}>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("mandos.manager.label")}</span>
        <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>{t(managerLabelKey(manager))}</span>
        {version && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>v{version}</span>}
      </div>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs, lineHeight: 1.4 }}>
        {t(managerDescKey(manager))}
      </div>
    </Card>
  );
};

const RemapBlock: FC = () => {
  const { t } = useI18n();
  const { config, scope, game, onScope, onSetButton, onReset } = useMandos();
  if (config?.kind !== "remap") return null;
  const buttons = config.buttons ?? [];
  const targetGroups = [
    { data: "", label: t("mandos.remap.default") },
    { label: t("mandos.targets.buttons"), options: (config.gamepad_targets ?? []).map((g) => ({ data: `gp:${g}`, label: prettyTarget(`gp:${g}`) })) },
    { label: t("mandos.targets.keys"), options: (config.key_targets ?? []).map((k) => ({ data: `key:${k}`, label: prettyTarget(`key:${k}`) })) },
  ];
  return (
    <Card title={t("mandos.remap.title")}>
      {buttons.length === 0 ? (
        // No remappable buttons for this model → nothing to scope per game. Show the
        // honest reason and point to Steam Input, no scope tab / reset for an empty editor.
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>
          {t(config.device_known === false ? "mandos.remap.uncalibrated" : "mandos.remap.nobuttons")}
        </div>
      ) : (
        <>
          <div style={{ marginBottom: theme.space.sm }}>
            <ProfileSelector
              scope={scope}
              gameName={game?.name ?? null}
              hasGameProfile={config.has_game_profile ?? false}
              globalLabel={t("tdp.scope.global")}
              inheritHint={t("mandos.inherit")}
              onScope={onScope}
            />
          </div>
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
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: `${theme.space.sm}px 0`, lineHeight: 1.4 }}>
            {t("mandos.remap.note")}
          </div>
          <DialogButton
            style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs }}
            onClick={onReset}
          >
            <LuRotateCcw size={14} /> {t("mandos.remap.reset")}
          </DialogButton>
        </>
      )}
    </Card>
  );
};

const SettingsBlock: FC = () => {
  const { t } = useI18n();
  const { config, onSetSetting } = useMandos();
  if (config?.kind !== "settings") return null;
  const label = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };
  return (
    <Card title={t("mandos.settings.title")}>
      <Row label={t("mandos.mode.label")}>
        <Dropdown
          rgOptions={(config.mode_options ?? []).map((m) => ({ data: m, label: label(`mandos.mode.${m}`, m) }))}
          selectedOption={config.mode ?? undefined}
          onChange={(o) => onSetSetting("mode", o.data as string)}
        />
      </Row>
      {config.paddles_as != null && (
        <Row label={t("mandos.paddles.label")}>
          <Dropdown
            rgOptions={(config.paddles_options ?? []).map((p) => ({ data: p, label: label(`mandos.paddles.${p}`, p) }))}
            selectedOption={config.paddles_as ?? undefined}
            onChange={(o) => onSetSetting("paddles_as", o.data as string)}
          />
        </Row>
      )}
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.sm, lineHeight: 1.4 }}>
        {t("mandos.settings.note")}
      </div>
    </Card>
  );
};

export function registerMandosBlocks(): void {
  registerBlock("manager", { sectionId: "mandos", Component: ManagerBlock });
  registerBlock("remap", {
    sectionId: "mandos",
    Component: RemapBlock,
    useAvailable: () => useMandos().config?.kind === "remap",
  });
  registerBlock("settings", {
    sectionId: "mandos",
    Component: SettingsBlock,
    useAvailable: () => useMandos().config?.kind === "settings",
  });
}
