import { FC, ReactNode } from "react";
import { DialogButton, Dropdown, ToggleField } from "@decky/ui";
import { LuActivity, LuGamepad2, LuRotateCcw, LuVibrate } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import {
  managerDescKey,
  managerLabelKey,
  prettyAction,
  prettyTarget,
  targetsToAction,
} from "../mandos/logic";
import { openKeyboardChordEditor } from "../mandos/KeyboardChordEditor";
import { useMandos } from "../mandos/mandosContext";
import {
  diagnosticOperationLabel,
  visibleDiagnosticGroups,
  type ControllerCapabilitySurface,
  type DiagnosticOperationLabel,
} from "../mandos/diagnostics";
import { useControllerDiagnostics } from "../mandos/useController";
import { ProfileSelector } from "../components/ProfileSelector";
import { ContainedSlider } from "../components/ContainedSlider";
import { registerBlock } from "../customize/blocks";

const Card: FC<{ title: string; children: ReactNode; icon?: ReactNode }> = ({ title, children, icon }) => (
  <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden" }}>
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary, marginBottom: theme.space.sm }}>
      {icon ?? <LuGamepad2 size={16} color={theme.color.accent} />} {title}
    </div>
    {children}
  </div>
);

const DiagnosticLine: FC<{ label: string; value: ReactNode }> = ({ label, value }) => (
  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: theme.space.md, padding: `${theme.space.xs}px 0`, borderBottom: `1px solid ${theme.color.hairline}` }}>
    <span style={{ minWidth: 0, fontSize: theme.font.caption, color: theme.color.textMuted }}>{label}</span>
    <span style={{ minWidth: 0, textAlign: "right", overflowWrap: "anywhere", fontSize: theme.font.caption, fontWeight: 700, color: theme.color.textPrimary }}>{value}</span>
  </div>
);

const DiagnosticHeading: FC<{ children: ReactNode }> = ({ children }) => (
  <div style={{ marginTop: theme.space.sm, fontSize: theme.font.caption, fontWeight: 700, color: theme.color.accent, letterSpacing: 0.7, textTransform: "uppercase" }}>
    {children}
  </div>
);

const statusColor = (status: DiagnosticOperationLabel): string => {
  if (status === "confirmed") return theme.color.ok;
  if (status === "failed") return theme.color.danger;
  return status === "unavailable" ? theme.color.textMuted : theme.color.accent;
};

const primitiveFieldSummary = (surface: ControllerCapabilitySurface): string => Object.entries(surface.fields)
  .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
  .slice(0, 6)
  .map(([key, value]) => `${key}: ${String(value)}`)
  .join(" · ");

const Row: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, padding: `${theme.space.xs}px 0` }}>
    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, letterSpacing: 0.2 }}>{label}</span>
    <div style={{ width: "100%", overflow: "hidden" }}>{children}</div>
  </div>
);

const RemapRow: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, padding: theme.space.xs, marginBottom: theme.space.xs, borderRadius: theme.radius.sm, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
    <span style={{ flex: "0 0 auto", minWidth: 38, height: 30, padding: `0 ${theme.space.sm}px`, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: theme.radius.sm, background: theme.color.accent, color: theme.color.onAccent, fontWeight: 700, fontSize: theme.font.body, letterSpacing: 0.5, boxShadow: "0 1px 2px rgba(0,0,0,0.4)" }}>
      {label}
    </span>
    <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>{children}</div>
  </div>
);

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
  const { config, scope, game, onScope, onSetButtonAction, onReset } = useMandos();
  if (config?.kind !== "remap") return null;
  const buttons = config.buttons ?? [];
  return (
    <Card title={t("mandos.remap.title")}>
      {buttons.length === 0 ? (
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
          {buttons.map((b) => {
            const action = targetsToAction(b.target ?? []);
            const selected = action.kind === "gamepad" ? `gp:${action.target}` : action.kind === "keyboard_chord" ? "shortcut" : "";
            const shortcutLabel = action.kind === "keyboard_chord"
              ? prettyAction(action)
              : t("mandos.remap.shortcut");
            const targetGroups = [
              { data: "", label: t("mandos.remap.default") },
              { label: t("mandos.targets.buttons"), options: (config.gamepad_targets ?? []).map((target) => ({ data: `gp:${target}`, label: prettyTarget(`gp:${target}`) })) },
              { label: t("mandos.targets.keys"), options: [{ data: "shortcut", label: shortcutLabel }] },
            ];
            return (
              <RemapRow key={b.source} label={b.label}>
                <Dropdown
                  rgOptions={targetGroups}
                  selectedOption={selected}
                  strDefaultLabel={t("mandos.remap.default")}
                  onChange={(option) => {
                    const value = option.data as string;
                    if (value === "shortcut") {
                      openKeyboardChordEditor({
                        initialKeys: action.kind === "keyboard_chord" ? action.keys : [],
                        keyTargets: config.key_targets ?? [],
                        onSave: (keys) => onSetButtonAction(b.source, { kind: "keyboard_chord", keys }),
                      });
                      return;
                    }
                    onSetButtonAction(
                      b.source,
                      value.startsWith("gp:")
                        ? { kind: "gamepad", target: value.slice(3) }
                        : { kind: "default" },
                    );
                  }}
                />
              </RemapRow>
            );
          })}
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: `${theme.space.sm}px 0`, lineHeight: 1.4 }}>
            {t("mandos.remap.note")}
          </div>
          {config.last_apply === false && (
            <div style={{ fontSize: theme.font.caption, color: theme.color.danger, marginBottom: theme.space.sm, lineHeight: 1.4 }}>
              {t(config.apply_error === "profile_conflict"
                ? "mandos.remap.conflict"
                : "mandos.remap.applyFailed")}
            </div>
          )}
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

const VibrationBlock: FC = () => {
  const { t } = useI18n();
  const {
    config, scope, game, onScope, onSetVibration, onTestVibration,
  } = useMandos();
  const vibration = config?.vibration;
  if (!vibration?.supported) return null;
  const sliderMin = vibration.min ?? 0;
  const sliderMax = vibration.max ?? 100;
  const sliderStep = vibration.step ?? 5;
  return (
    <Card title={t("mandos.vibration.title")}>
      <div style={{ marginBottom: theme.space.sm }}>
        <ProfileSelector
          scope={scope}
          gameName={game?.name ?? null}
          hasGameProfile={config?.has_game_profile ?? false}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("mandos.vibration.inherit")}
          onScope={onScope}
        />
      </div>
      <ToggleField
        label={t("mandos.vibration.enabled")}
        description={t("mandos.vibration.enabled.desc")}
        checked={vibration.enabled === true}
        onChange={(enabled) => onSetVibration({ enabled })}
        bottomSeparator="none"
      />
      {vibration.persistent && vibration.mode === "gain" && vibration.value != null && (
        <ContainedSlider
          label={t("mandos.vibration.intensity")}
          value={vibration.value}
          min={sliderMin}
          max={sliderMax}
          step={sliderStep}
          showValue
          onChange={(value) => onSetVibration({ value })}
        />
      )}
      {vibration.persistent && vibration.mode === "dual" && (
        <>
          {vibration.left != null && (
            <ContainedSlider
              label={t("mandos.vibration.left")}
              value={vibration.left}
              min={sliderMin}
              max={sliderMax}
              step={sliderStep}
              showValue
              onChange={(left) => onSetVibration({ left })}
            />
          )}
          {vibration.right != null && (
            <ContainedSlider
              label={t("mandos.vibration.right")}
              value={vibration.right}
              min={sliderMin}
              max={sliderMax}
              step={sliderStep}
              showValue
              onChange={(right) => onSetVibration({ right })}
            />
          )}
        </>
      )}
      {vibration.test_supported && (
        <DialogButton
          disabled={vibration.enabled !== true}
          style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs }}
          onClick={() => onTestVibration(1)}
        >
          <LuVibrate size={15} /> {t("mandos.vibration.test")}
        </DialogButton>
      )}
      {vibration.persistent && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.sm, lineHeight: 1.4 }}>
          {t(vibration.readback
            ? "mandos.vibration.note.readback"
            : "mandos.vibration.note.accepted")}
        </div>
      )}
      {vibration.last_apply === false && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.danger, marginTop: theme.space.sm, lineHeight: 1.4 }}>
          {t("mandos.vibration.applyFailed")}
        </div>
      )}
    </Card>
  );
};

const DiagnosticsBlock: FC = () => {
  const { t } = useI18n();
  const diagnostics = useControllerDiagnostics();
  if (!diagnostics) return null;
  const groups = visibleDiagnosticGroups(diagnostics);
  if (groups.length === 0) return null;
  const capability = (surface: ControllerCapabilitySurface) => {
    const status = surface.availability === "supported" ? "confirmed" : "unavailable";
    const detail = primitiveFieldSummary(surface);
    return (
      <>
        <DiagnosticLine
          label={t("mandos.diagnostics.owner")}
          value={surface.owner}
        />
        <DiagnosticLine
          label={t("mandos.diagnostics.availability")}
          value={<span style={{ color: statusColor(status) }}>{t(`mandos.diagnostics.availability.${surface.availability}`)}</span>}
        />
        <DiagnosticLine
          label={t("mandos.diagnostics.readback")}
          value={t(`mandos.diagnostics.readback.${surface.readback}`)}
        />
        <DiagnosticLine
          label={t("mandos.diagnostics.scope")}
          value={surface.scope.map((scope) => t(`mandos.diagnostics.scope.${scope}`)).join(" · ")}
        />
        {detail && <DiagnosticLine label={t("mandos.diagnostics.values")} value={detail} />}
      </>
    );
  };

  return (
    <Card
      title={t("mandos.diagnostics.title")}
      icon={<LuActivity size={16} color={theme.color.accent} />}
    >
      {groups.includes("sources") && (
        <>
          <DiagnosticHeading>{t("mandos.diagnostics.sources")}</DiagnosticHeading>
          {diagnostics.sources.map((source, index) => (
            <DiagnosticLine
              key={`${source.manager}-${index}`}
              label={source.name ?? t(`mandos.manager.${source.manager === "inputplumber" ? "ip" : "hhd"}`)}
              value={[
                source.version ? `v${source.version}` : null,
                source.source_count != null ? t("mandos.diagnostics.sourceCount", { count: source.source_count }) : null,
              ].filter(Boolean).join(" · ") || t("mandos.diagnostics.detected")}
            />
          ))}
        </>
      )}
      {groups.includes("batteries") && (
        <>
          <DiagnosticHeading>{t("mandos.diagnostics.batteries")}</DiagnosticHeading>
          {diagnostics.batteries.map((battery) => (
            <DiagnosticLine key={battery.label} label={battery.label} value={`${battery.percent}%`} />
          ))}
        </>
      )}
      {groups.includes("inputs") && (
        <>
          <DiagnosticHeading>{t("mandos.diagnostics.inputs")}</DiagnosticHeading>
          {(diagnostics.inputs.buttons ?? []).map((button) => (
            <DiagnosticLine key={button.source} label={button.label} value={button.source} />
          ))}
        </>
      )}
      {diagnostics.motion && (
        <>
          <DiagnosticHeading>{t("mandos.diagnostics.motion")}</DiagnosticHeading>
          {capability(diagnostics.motion)}
        </>
      )}
      {diagnostics.vibration && (
        <>
          <DiagnosticHeading>{t("mandos.diagnostics.vibration")}</DiagnosticHeading>
          {capability(diagnostics.vibration)}
        </>
      )}
      {groups.includes("operations") && (
        <>
          <DiagnosticHeading>{t("mandos.diagnostics.operations")}</DiagnosticHeading>
          {Object.entries(diagnostics.last_operations).map(([name, operation]) => {
            const status = diagnosticOperationLabel(operation);
            return (
              <DiagnosticLine
                key={name}
                label={operation.operation ?? name}
                value={<span style={{ color: statusColor(status) }}>{t(`mandos.diagnostics.status.${status}`)}</span>}
              />
            );
          })}
        </>
      )}
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
  registerBlock("vibration", {
    sectionId: "mandos",
    Component: VibrationBlock,
    useAvailable: () => useMandos().config?.vibration?.supported === true,
  });
  registerBlock("diagnostics", {
    sectionId: "mandos",
    Component: DiagnosticsBlock,
  });
}
