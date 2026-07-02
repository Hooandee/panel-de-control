import { FC, ReactNode } from "react";
import { Focusable } from "@decky/ui";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";

export interface TabItem {
  id: string;
  icon: ReactNode;
  label: string;
  // Optional adornment rendered after the label on the active tab (e.g. an update dot).
  badge?: ReactNode;
}

interface TabBarProps {
  tabs: TabItem[];
  activeId: string;
  onSelect: (id: string) => void;
}

/**
 * Segmented tab bar — the control-center navigator. The ACTIVE tab shows
 * icon + label and grows; inactive tabs are compact icon-only buttons. This
 * keeps many tabs readable in the narrow QAM panel and scales as sections grow
 * (a dropdown could later replace this with zero change to the registry).
 */
export const TabBar: FC<TabBarProps> = ({ tabs, activeId, onSelect }) => {
  return (
    <Focusable style={segmentGroupStyle}>
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <Focusable
            key={tab.id}
            style={{
              ...segmentItemStyle(active),
              flex: active ? 1 : "0 0 auto",
              padding: active ? "6px 10px" : "6px 9px",
            }}
            aria-label={tab.label}
            // Focusable fires onActivate on gamepad, onClick on pointer/touch.
            onActivate={() => onSelect(tab.id)}
            onClick={() => onSelect(tab.id)}
          >
            {tab.icon}
            {active && <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{tab.label}</span>}
            {/* Alert badge shows on any tab state (icon-only or expanded) so an
                update is noticeable even when the tab isn't active. */}
            {tab.badge}
          </Focusable>
        );
      })}
    </Focusable>
  );
};
