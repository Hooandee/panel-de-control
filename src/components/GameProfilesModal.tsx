import { FC, useEffect, useMemo, useState } from "react";
import { ModalRoot, showModal, Focusable } from "@decky/ui";
import { LuTrash2, LuGamepad2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { GameProfileRow, listGameProfiles, resetGameProfiles } from "../api";
import { configuredSections, SectionId } from "../system/gameProfiles";
import { isNonSteamKey, nonSteamName } from "../tdp/gameIdentity";
import { FocusRoot } from "./FocusRoot";

type T = (key: string, params?: Record<string, string | number>) => string;
type SectionLine = { label: string; text: string; dim: boolean };

/** Resolve a stored appid to a display name. Steam games via the app store (missing =
 *  uninstalled); non-Steam shortcuts carry their name in the "ns:" key. */
function resolveName(appid: string): { name: string; installed: boolean } {
  if (isNonSteamKey(appid)) return { name: nonSteamName(appid), installed: true };
  try {
    // appStore is an internal Steam global (not in @decky types) — guarded.
    const ov = (window as unknown as { appStore?: { GetAppOverviewByAppID?: (id: number) => { display_name?: string } | null } })
      .appStore?.GetAppOverviewByAppID?.(Number(appid));
    if (ov?.display_name) return { name: ov.display_name, installed: true };
  } catch {
    /* ignore */
  }
  return { name: appid, installed: false };
}

/** One translated summary line per configured section: a label + a short value. */
function sectionLine(section: SectionId, row: GameProfileRow, t: T): SectionLine | null {
  if (section === "tdp" && row.tdp) {
    const extra = [row.tdp.auto ? t("gameProfiles.auto") : "", row.tdp.gpu ? "GPU" : ""].filter(Boolean);
    return { label: t("gameProfiles.sec.tdp"), text: [`${row.tdp.pl1} W`, ...extra].join(" · "), dim: row.tdp.follows_global };
  }
  if (section === "fan" && row.fan) {
    return { label: t("gameProfiles.sec.fan"), text: t(`fans.preset.${row.fan.preset}`), dim: row.fan.follows_global };
  }
  if (section === "color" && row.color) {
    const extra = [row.color.calibrated ? t("gameProfiles.calibrated") : "", row.color.hdr ? "HDR" : ""].filter(Boolean);
    return { label: t("gameProfiles.sec.color"), text: [t("gameProfiles.sat", { v: row.color.saturation }), ...extra].join(" · "), dim: row.color.follows_global };
  }
  if (section === "cpu" && row.cpu) {
    const parts = [
      `SMT ${row.cpu.smt ? "on" : "off"}`,
      `${t("gameProfiles.boost")} ${row.cpu.boost ? "on" : "off"}`,
    ];
    if (row.cpu.cores != null) parts.push(t("gameProfiles.cores", { n: row.cpu.cores }));
    return { label: t("gameProfiles.sec.cpu"), text: parts.join(" · "), dim: row.cpu.follows_global };
  }
  if (section === "mandos" && row.mandos) {
    return { label: t("gameProfiles.sec.mandos"), text: t("gameProfiles.buttons", { n: row.mandos.count }), dim: row.mandos.follows_global };
  }
  if (section === "audio" && row.audio) {
    return { label: t("gameProfiles.sec.audio"), text: t("gameProfiles.audioCustom"), dim: row.audio.follows_global };
  }
  return null;
}

const GameRow: FC<{ row: GameProfileRow; onReset: (appid: string) => void }> = ({ row, onReset }) => {
  const { t } = useI18n();
  const [confirm, setConfirm] = useState(false);
  // Auto-revert the armed "tap again" state so it doesn't stay stuck (e.g. if the user
  // changes their mind, or a reset RPC failed).
  useEffect(() => {
    if (!confirm) return;
    const id = setTimeout(() => setConfirm(false), 3000);
    return () => clearTimeout(id);
  }, [confirm]);
  const { name, installed } = useMemo(() => resolveName(row.appid), [row.appid]);
  const lines = useMemo(
    () => configuredSections(row).map((s) => sectionLine(s, row, t)).filter((l): l is SectionLine => l !== null),
    [row, t],
  );

  return (
    <div style={{ ...theme.card, padding: theme.space.md, marginBottom: theme.space.sm, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, marginBottom: theme.space.xs }}>
        <LuGamepad2 size={16} color={theme.color.accent} style={{ flexShrink: 0 }} />
        <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {name}
        </span>
        {!installed && (
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, fontStyle: "italic", flexShrink: 0 }}>
            {t("gameProfiles.uninstalled")}
          </span>
        )}
      </div>

      {lines.map((l) => (
        <div key={l.label} style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.5, opacity: l.dim ? 0.5 : 1 }}>
          <span style={{ color: theme.color.textPrimary, fontWeight: 600 }}>{l.label}</span> {l.text}
          {l.dim && <span> · {t("gameProfiles.followsGlobal")}</span>}
        </div>
      ))}

      <Focusable
        style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs,
          marginTop: theme.space.sm, padding: "6px 12px", borderRadius: theme.radius.sm,
          background: confirm ? theme.color.danger : theme.color.surfaceRaised,
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
          color: confirm ? "#ffffff" : theme.color.textPrimary, fontSize: theme.font.body, cursor: "pointer",
        }}
        onActivate={() => (confirm ? onReset(row.appid) : setConfirm(true))}
        onClick={() => (confirm ? onReset(row.appid) : setConfirm(true))}
      >
        <LuTrash2 size={14} /> {confirm ? t("gameProfiles.resetConfirm") : t("gameProfiles.reset")}
      </Focusable>
    </div>
  );
};

const GameProfilesBody: FC = () => {
  const { t } = useI18n();
  const [rows, setRows] = useState<GameProfileRow[] | null>(null);

  useEffect(() => {
    listGameProfiles().then(setRows).catch(() => setRows([]));
  }, []);

  const onReset = (appid: string) => {
    resetGameProfiles(appid).then(setRows).catch(() => {});
  };

  return (
    <div style={{ padding: theme.space.md }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: theme.color.textPrimary, marginBottom: theme.space.xs }}>
        {t("gameProfiles.title")}
      </div>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginBottom: theme.space.md, lineHeight: 1.4 }}>
        {t("gameProfiles.desc")}
      </div>
      {rows === null ? (
        <Loading />
      ) : rows.length === 0 ? (
        <div style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>{t("gameProfiles.empty")}</div>
      ) : (
        rows.map((row) => <GameRow key={row.appid} row={row} onReset={onReset} />)
      )}
    </div>
  );
};

const GameProfilesModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <GameProfilesBody />
    </FocusRoot>
  </ModalRoot>
);

/** Open the full-screen per-game profile overview (Ajustes). */
export function openGameProfilesModal(): void {
  showModal(<GameProfilesModal />, window);
}
