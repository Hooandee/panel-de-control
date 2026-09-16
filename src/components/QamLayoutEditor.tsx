import { ButtonItem } from "@decky/ui";
import { type FC, type ReactNode, useSyncExternalStore } from "react";
import {
  LuChevronDown,
  LuChevronUp,
  LuEye,
  LuEyeOff,
  LuLockKeyhole,
  LuPanelTop,
  LuPin,
  LuPinOff,
  LuPlug,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import {
  completeQamOrder,
  isNativeQamToken,
  type QamEntryToken,
} from "../qam/layout";
import {
  getQamRuntimeSnapshot,
  subscribeQamRuntime,
} from "../qam/runtime";
import { resetQamLayout, saveQamLayout, useQamLayout } from "../qam/store";
import type { QamViewDescriptor } from "../qam/viewCatalog";
import { theme } from "../theme";
import { reloadDeckyAfterClosingMenus } from "../system/reloadDecky";
import { IconAction } from "./IconAction";

const STEAM_NATIVE_QAM_LABELS: Readonly<Record<string, string>> = {
  "0": "customize.qam.native.notifications",
  "3": "customize.qam.native.friends",
  "4": "customize.qam.native.quickSettings",
  "5": "customize.qam.native.performance",
  "6": "customize.qam.native.help",
  "7": "customize.qam.native.soundtracks",
};

export function nativeQamLabelKey(key: unknown): string | null {
  const observed = STEAM_NATIVE_QAM_LABELS[String(key)];
  if (observed) return observed;
  const normalized = String(key).toLowerCase().replace(/[^a-z]/g, "");
  if (normalized.includes("friend")) return "customize.qam.native.friends";
  if (normalized.includes("soundtrack") || normalized.includes("music")) {
    return "customize.qam.native.soundtracks";
  }
  if (normalized.includes("help")) return "customize.qam.native.help";
  if (normalized.includes("notification")) return "customize.qam.native.notifications";
  if (normalized.includes("performance")) return "customize.qam.native.performance";
  if (normalized.includes("setting")) return "customize.qam.native.quickSettings";
  return null;
}

const rowStyle: React.CSSProperties = {
  ...theme.card,
  display: "flex",
  alignItems: "center",
  gap: theme.space.sm,
  padding: `${theme.space.sm + 2}px ${theme.space.md}px`,
};

const rowIconStyle: React.CSSProperties = {
  width: 30,
  height: 30,
  flexShrink: 0,
  borderRadius: theme.radius.sm,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: theme.color.accent,
  background: `rgba(${theme.color.accentRgb},0.14)`,
};

const rowLabelStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  color: theme.color.textPrimary,
};

function toggleToken(tokens: QamEntryToken[], token: QamEntryToken): QamEntryToken[] {
  return tokens.includes(token)
    ? tokens.filter((entry) => entry !== token)
    : [...tokens, token];
}

export const QamLayoutEditor: FC<{ catalog: QamViewDescriptor[] }> = ({ catalog }) => {
  const { t } = useI18n();
  const layout = useQamLayout();
  const runtime = useSyncExternalStore(
    subscribeQamRuntime,
    getQamRuntimeSnapshot,
    getQamRuntimeSnapshot,
  );
  const nativeByToken = new Map(runtime.inventory.map((entry) => [entry.token, entry]));
  const panelByToken = new Map(catalog.map((entry) => [entry.token, entry]));
  const tokens = completeQamOrder(
    layout.order,
    [...nativeByToken.keys(), ...panelByToken.keys()],
  );

  const saveOrder = (order: QamEntryToken[]) => saveQamLayout({ ...layout, order });
  const move = (token: QamEntryToken, direction: -1 | 1) => {
    const index = tokens.indexOf(token);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= tokens.length) return;
    const next = [...tokens];
    [next[index], next[target]] = [next[target], next[index]];
    saveOrder(next);
  };
  const toggleNative = (token: QamEntryToken) => {
    saveQamLayout({
      ...layout,
      order: tokens,
      hiddenNative: toggleToken(layout.hiddenNative, token),
    });
  };
  const togglePanel = (token: QamEntryToken) => {
    saveQamLayout({
      ...layout,
      order: tokens,
      pinnedViews: toggleToken(layout.pinnedViews, token),
    });
  };
  const renderRow = (
    token: QamEntryToken,
    label: string,
    icon: ReactNode,
    active: boolean,
    index: number,
  ) => (
    <div key={token} style={{ ...rowStyle, opacity: active ? 1 : 0.55 }}>
      <span style={rowIconStyle}>{icon}</span>
      <span style={rowLabelStyle}>{label}</span>
      <IconAction
        label={`${t("customize.moveUp")} ${label}`}
        color={index === 0 ? theme.color.textMuted : theme.color.accent}
        disabled={index === 0}
        onTap={() => move(token, -1)}
      >
        <LuChevronUp size={18} />
      </IconAction>
      <IconAction
        label={`${t("customize.moveDown")} ${label}`}
        color={index === tokens.length - 1 ? theme.color.textMuted : theme.color.accent}
        disabled={index === tokens.length - 1}
        onTap={() => move(token, 1)}
      >
        <LuChevronDown size={18} />
      </IconAction>
      {isNativeQamToken(token) ? (
        <IconAction
          label={`${t(active ? "customize.hide" : "customize.show")} ${label}`}
          color={theme.color.textMuted}
          onTap={() => toggleNative(token)}
        >
          {active ? <LuEye size={18} /> : <LuEyeOff size={18} />}
        </IconAction>
      ) : (
        <IconAction
          label={`${t(active ? "customize.qam.unpin" : "customize.qam.pin")} ${label}`}
          color={active ? theme.color.accent : theme.color.textMuted}
          onTap={() => togglePanel(token)}
        >
          {active ? <LuPinOff size={18} /> : <LuPin size={18} />}
        </IconAction>
      )}
    </div>
  );

  let runtimeStatus: ReactNode;
  if (runtime.restartRequired) {
    runtimeStatus = (
      <>
        <div style={{ fontSize: theme.font.caption, color: theme.color.warn }}>
          {t("customize.qam.restart")}
        </div>
        <ButtonItem layout="below" onClick={reloadDeckyAfterClosingMenus}>
          {t("customize.qam.restartButton")}
        </ButtonItem>
      </>
    );
  } else if (runtime.applied) {
    runtimeStatus = (
      <div style={{ fontSize: theme.font.caption, color: theme.color.ok }}>
        {t("customize.qam.applied")}
      </div>
    );
  } else {
    runtimeStatus = (
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t(
          !runtime.initialized || runtime.reason === "awaiting_render"
            ? "customize.qam.loading"
            : "customize.qam.unavailable",
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t("customize.qam.desc")}
      </div>
      {tokens.map((token, index) => {
        const native = nativeByToken.get(token);
        if (native) {
          const labelKey = nativeQamLabelKey(native.key);
          const label = labelKey
            ? t(labelKey)
            : `${t("customize.qam.native")} · ${String(native.key)}`;
          const icon = (native.entry as { icon?: ReactNode }).icon ?? <LuPanelTop size={17} />;
          return renderRow(token, label, icon, !layout.hiddenNative.includes(token), index);
        }
        const panel = panelByToken.get(token);
        if (!panel) return null;
        const label = panel.label || t(panel.labelKey);
        return renderRow(
          token,
          label,
          panel.icon(17),
          layout.pinnedViews.includes(token),
          index,
        );
      })}
      <div style={rowStyle}>
        <span style={rowIconStyle}><LuPlug size={17} /></span>
        <span style={{ flex: 1, color: theme.color.textPrimary }}>{t("customize.qam.decky")}</span>
        <span style={{ display: "flex", alignItems: "center", gap: theme.space.xs, color: theme.color.textMuted, fontSize: theme.font.caption }}>
          <LuLockKeyhole size={15} /> {t("customize.qam.protected")}
        </span>
      </div>
      {runtimeStatus}
      <ButtonItem layout="below" onClick={resetQamLayout}>
        {t("customize.qam.reset")}
      </ButtonItem>
    </div>
  );
};
