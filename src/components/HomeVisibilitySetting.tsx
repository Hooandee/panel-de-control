import { Focusable, ToggleField } from "@decky/ui";
import { FC, useRef } from "react";
import { LuLayoutDashboard, LuPanelsTopLeft } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";

export const HomeVisibilitySetting: FC<{
  value: boolean;
  onChange: (value: boolean) => void;
  deviceHeaderValue: boolean;
  onDeviceHeaderChange: (value: boolean) => void;
}> = ({ value, onChange, deviceHeaderValue, onDeviceHeaderChange }) => {
  const { t } = useI18n();
  const locked = useRef(new Set<boolean>());
  const selectView = (nextValue: boolean) => () => {
    if (value === nextValue || locked.current.has(nextValue)) return;
    locked.current.add(nextValue);
    try {
      onChange(nextValue);
    } finally {
      queueMicrotask(() => locked.current.delete(nextValue));
    }
  };

  return (
    <>
      <div
        role="group"
        aria-label={t("customize.home")}
        data-description={t("customize.home.desc")}
        style={{ marginBottom: theme.space.md }}
      >
        <div style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 600 }}>
          {t("customize.home")}
        </div>
        <div
          style={{
            marginTop: 2,
            marginBottom: theme.space.sm,
            color: theme.color.textMuted,
            fontSize: theme.font.caption,
            lineHeight: 1.35,
          }}
        >
          {t("customize.home.desc")}
        </div>
        <div style={{ ...segmentGroupStyle, width: "100%", boxSizing: "border-box" }}>
          <Focusable
            role="button"
            aria-label={t("customize.home.dashboard")}
            aria-pressed={value}
            onActivate={selectView(true)}
            onClick={selectView(true)}
            style={{ ...segmentItemStyle(value), flex: 1, minHeight: 34, padding: "6px 8px" }}
          >
            <LuLayoutDashboard size={16} aria-hidden="true" />
            {t("customize.home.dashboard")}
          </Focusable>
          <Focusable
            role="button"
            aria-label={t("customize.home.tabs")}
            aria-pressed={!value}
            onActivate={selectView(false)}
            onClick={selectView(false)}
            style={{ ...segmentItemStyle(!value), flex: 1, minHeight: 34, padding: "6px 8px" }}
          >
            <LuPanelsTopLeft size={16} aria-hidden="true" />
            {t("customize.home.tabs")}
          </Focusable>
        </div>
      </div>
      <ToggleField
        label={t("customize.deviceHeader")}
        description={t("customize.deviceHeader.desc")}
        checked={deviceHeaderValue}
        onChange={onDeviceHeaderChange}
        bottomSeparator="none"
      />
    </>
  );
};
