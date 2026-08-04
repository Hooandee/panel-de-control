import { FC, ReactNode, useLayoutEffect, useRef } from "react";
import { Dropdown } from "@decky/ui";

import { theme } from "../theme";

interface SurfaceProps {
  children: ReactNode;
}

export const CompactFieldSurface: FC<SurfaceProps> = ({ children }) => (
  <div
    data-testid="compact-field-surface"
    style={{
      width: "100%",
      minWidth: 0,
      boxSizing: "border-box",
      padding: theme.space.sm,
      marginBottom: theme.space.sm,
      borderRadius: theme.radius.sm,
      background: "rgba(255,255,255,0.025)",
      boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    }}
  >
    {children}
  </div>
);

interface ChoiceOption {
  data: string;
  label: ReactNode;
}

interface ChoiceProps {
  label: string;
  options: readonly ChoiceOption[];
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

interface ScrollPosition {
  element: HTMLElement;
  top: number;
  left: number;
}

const captureScrollPositions = (origin: HTMLElement | null): ScrollPosition[] => {
  const positions: ScrollPosition[] = [];
  for (let element = origin?.parentElement ?? null; element; element = element.parentElement) {
    if (element.scrollTop !== 0 || element.scrollLeft !== 0) {
      positions.push({
        element,
        top: element.scrollTop,
        left: element.scrollLeft,
      });
    }
  }
  return positions;
};

const restoreScrollPositions = (positions: readonly ScrollPosition[]): void => {
  for (const { element, top, left } of positions) {
    element.scrollTop = top;
    element.scrollLeft = left;
  }
};

const restoreAfterDeckyFocus = (
  positions: readonly ScrollPosition[],
): void => {
  restoreScrollPositions(positions);
  if (typeof requestAnimationFrame !== "function") return;
  requestAnimationFrame(() => {
    restoreScrollPositions(positions);
    requestAnimationFrame(() => restoreScrollPositions(positions));
  });
};

export const CompactChoiceField: FC<ChoiceProps> = ({
  label, options, value, disabled, onChange,
}) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const scrollPositions = useRef<ScrollPosition[]>([]);

  useLayoutEffect(() => {
    restoreAfterDeckyFocus(scrollPositions.current);
  }, [value]);

  return (
    <div ref={rootRef} style={{ width: "100%", minWidth: 0 }}>
      <CompactFieldSurface>
        <div
          data-testid="compact-field-label"
          style={{
            minWidth: 0,
            marginBottom: theme.space.xs,
            color: disabled ? theme.color.textMuted : theme.color.textPrimary,
            fontSize: theme.font.caption,
            lineHeight: 1.35,
            overflowWrap: "anywhere",
          }}
        >
          {label}
        </div>
        <div
          data-testid="compact-field-control"
          style={{ width: "100%", maxWidth: "100%", minWidth: 0 }}
        >
          <Dropdown
            rgOptions={[...options]}
            selectedOption={value}
            disabled={disabled}
            menuLabel={label}
            renderButtonValue={(selectedLabel) => (
              <span
                data-testid="compact-field-value"
                style={{
                  display: "block",
                  width: "100%",
                  minWidth: 0,
                  maxWidth: "100%",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {selectedLabel}
              </span>
            )}
            onChange={(option) => {
              const next = option.data as string;
              if (next !== value && options.some((candidate) => candidate.data === next)) {
                scrollPositions.current = captureScrollPositions(rootRef.current);
                onChange(next);
                restoreAfterDeckyFocus(scrollPositions.current);
              }
            }}
          />
        </div>
      </CompactFieldSurface>
    </div>
  );
};

interface NoticeProps {
  children: ReactNode;
  tone: "danger" | "warning" | "muted";
}

export const InlineNotice: FC<NoticeProps> = ({ children, tone }) => {
  const appearance = tone === "danger"
    ? { color: theme.color.danger, background: "rgba(224,90,90,0.10)" }
    : tone === "warning"
      ? { color: theme.color.warn, background: "rgba(255,180,84,0.10)" }
      : { color: theme.color.textMuted, background: "rgba(255,255,255,0.035)" };
  return (
    <div role="status" aria-live="polite" aria-atomic="true" style={{
      width: "100%",
      minWidth: 0,
      boxSizing: "border-box",
      marginTop: theme.space.sm,
      padding: `${theme.space.xs + 2}px ${theme.space.sm}px`,
      borderRadius: theme.radius.sm,
      background: appearance.background,
      color: appearance.color,
      fontSize: theme.font.caption,
      lineHeight: 1.4,
      overflowWrap: "anywhere",
    }}>
      {children}
    </div>
  );
};
