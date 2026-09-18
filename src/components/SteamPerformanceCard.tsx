import {
  Component,
  type FC,
  type ReactNode,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  LuCircleAlert,
  LuCircleCheck,
  LuLoaderCircle,
  LuMonitorCog,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import type {
  SteamPerformanceComponent,
  SteamPerformanceComponentId,
  SteamPerformanceRow,
} from "../steam/performanceSurface";
import { useSteamPerformanceSurface } from "../steam/useSteamPerformanceSurface";
import { theme } from "../theme";
import { Collapsible } from "./Collapsible";

const LONG_AUTO_LABELS = new Set([
  "automatic",
  "automatisch",
  "automatico",
  "automático",
]);
const SCALING_SLIDER_SCALE = 0.86;
const RESET_SEPARATOR_CSS = `
  [data-pdc-steam-reset] .Panel.Focusable::after {
    display: none !important;
  }
`;
const SCALING_CONTROL_IDS = new Set<SteamPerformanceComponentId>([
  "combinedScaling",
  "splitScalingFilter",
  "scalingMode",
  "sharpness",
  "fsrSharpness",
  "nisSharpness",
]);
const FRAME_RATE_SLIDER_CONTROL_IDS = new Set<SteamPerformanceComponentId>([
  "legacyFrameRate",
  "appFrameRate",
  "refreshRate",
]);

const shortenAutoLabel = (root: HTMLElement): void => {
  const walker = root.ownerDocument.createTreeWalker(root, 4);
  let node = walker.nextNode();
  while (node) {
    const value = node.textContent ?? "";
    const label = value.trim().toLocaleLowerCase();
    if (LONG_AUTO_LABELS.has(label)) {
      node.textContent = value.replace(value.trim(), "Auto");
    }
    node = walker.nextNode();
  }
};

const forEachNativeSliderLabel = (
  root: HTMLElement,
  visit: (label: HTMLElement) => void,
): void => {
  root.querySelectorAll<HTMLElement>('[role="slider"][aria-labelledby]').forEach((slider) => {
    const labelIds = slider.getAttribute("aria-labelledby")?.split(/\s+/) ?? [];
    labelIds.forEach((labelId) => {
      const label = root.ownerDocument.getElementById(labelId);
      if (!label || !root.contains(label)) return;
      visit(label);
    });
  });
};

const insetNativeSliderTitles = (root: HTMLElement): void => {
  forEachNativeSliderLabel(root, (label) => {
    label.style.paddingInline = `${theme.space.sm}px`;
    label.style.boxSizing = "border-box";
  });
};

const scaleNativeSliderRows = (root: HTMLElement): void => {
  root.querySelectorAll<HTMLElement>('[role="slider"]').forEach((slider) => {
    const row = slider.closest<HTMLElement>('[role="button"]');
    if (!row || !root.contains(row)) return;
    row.style.transform = `scale(${SCALING_SLIDER_SCALE})`;
    row.style.transformOrigin = "left top";
  });
};

const keepNativeSliderValuesInline = (root: HTMLElement): void => {
  forEachNativeSliderLabel(root, (label) => {
    const value = Array.from(label.children).find((child) => (
      child.getAttribute("aria-hidden") === "true"
    ));
    const ElementType = root.ownerDocument.defaultView?.HTMLElement;
    if (!ElementType || !(value instanceof ElementType)) return;
    if (value.style.whiteSpace !== "nowrap") value.style.whiteSpace = "nowrap";
    if (value.style.flexShrink !== "0") value.style.flexShrink = "0";
  });
};

const NativeSliderLayout: FC<{
  children: ReactNode;
  compact: boolean;
  compactAuto: boolean;
}> = ({
  children,
  compact,
  compactAuto,
}) => {
  const rootRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const reconcile = () => {
      keepNativeSliderValuesInline(root);
      if (compact) {
        scaleNativeSliderRows(root);
        insetNativeSliderTitles(root);
        if (compactAuto) shortenAutoLabel(root);
      }
    };
    reconcile();
    const Observer = root.ownerDocument.defaultView?.MutationObserver;
    if (!Observer) return;
    const observer = new Observer(reconcile);
    observer.observe(root, { childList: true, characterData: true, subtree: true });
    return () => observer.disconnect();
  }, [compact, compactAuto]);

  return (
    <div
      ref={rootRef}
      data-testid={compact ? "steam-scaling-slider-viewport" : undefined}
      style={compact ? {
        width: `calc(100% - ${theme.space.sm}px)`,
        minWidth: 0,
        marginInline: "auto",
        overflow: "visible",
        contain: "layout",
      } : { display: "contents" }}
    >
      {children}
    </div>
  );
};

interface NativeControlBoundaryProps {
  id: SteamPerformanceComponentId;
  Control: SteamPerformanceComponent;
  onError: (id: SteamPerformanceComponentId, control: SteamPerformanceComponent) => void;
  onRecovery: (id: SteamPerformanceComponentId, control: SteamPerformanceComponent) => void;
}

interface NativeControlBoundaryState {
  failed: boolean;
}

class NativeControlBoundary extends Component<
  NativeControlBoundaryProps,
  NativeControlBoundaryState
> {
  private retryCount = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  state: NativeControlBoundaryState = { failed: false };

  static getDerivedStateFromError(): NativeControlBoundaryState {
    return { failed: true };
  }

  componentDidCatch(): void {
    this.props.onError(this.props.id, this.props.Control);
    if (this.retryCount >= 1) return;

    this.retryCount += 1;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.setState({ failed: false });
    }, 2000);
  }

  componentDidUpdate(
    previousProps: NativeControlBoundaryProps,
    previousState: NativeControlBoundaryState,
  ): void {
    if (previousProps.Control !== this.props.Control) {
      this.clearRetry();
      this.retryCount = 0;
      this.props.onRecovery(this.props.id, previousProps.Control);
      if (this.state.failed) this.setState({ failed: false });
      return;
    }

    if (previousState.failed && !this.state.failed) {
      this.retryCount = 0;
      this.props.onRecovery(this.props.id, this.props.Control);
    }
  }

  componentWillUnmount(): void {
    this.clearRetry();
  }

  private clearRetry(): void {
    if (this.retryTimer === null) return;
    clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  render() {
    if (this.state.failed) return null;
    const { Control, id } = this.props;
    const compact = SCALING_CONTROL_IDS.has(id);
    if (!compact && !FRAME_RATE_SLIDER_CONTROL_IDS.has(id)) return <Control />;
    return (
      <NativeSliderLayout compact={compact} compactAuto={id === "scalingMode"}>
        <Control />
      </NativeSliderLayout>
    );
  }
}

const GROUPS: ReadonlyArray<{
  label: string;
  ids: ReadonlySet<SteamPerformanceComponentId>;
}> = [
  {
    label: "steam.performance.group.display",
    ids: new Set(["legacyFrameRate", "appFrameRate", "disableFrameLimit", "refreshRate"]),
  },
  {
    label: "steam.performance.group.fluidity",
    ids: new Set(["variableResolution", "vrr", "allowTearing"]),
  },
  {
    label: "steam.performance.group.scaling",
    ids: SCALING_CONTROL_IDS,
  },
];

interface PerformanceGroupProps {
  label: string;
  rows: SteamPerformanceRow[];
  hidden: boolean;
  renderRow: (row: SteamPerformanceRow) => ReactNode;
}

const PerformanceGroup: FC<PerformanceGroupProps> = ({ label, rows, hidden, renderRow }) => (
  <section
    role="group"
    aria-label={label}
    hidden={hidden}
    style={{
      display: hidden ? "none" : "flex",
      flexDirection: "column",
      gap: theme.space.sm,
    }}
  >
    <div style={{ ...theme.sectionLabel, paddingLeft: 2 }}>{label}</div>
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {rows.map(renderRow)}
    </div>
  </section>
);

interface SteamPerformanceCardProps {
  profileScope?: "global" | "game";
  runningGameId?: number | null;
}

export const SteamPerformanceCard: FC<SteamPerformanceCardProps> = ({
  profileScope = "global",
  runningGameId = null,
}) => {
  const { t } = useI18n();
  const surface = useSteamPerformanceSurface(profileScope, runningGameId);
  const [failures, setFailures] = useState(() => (
    new Map<SteamPerformanceComponentId, SteamPerformanceComponent>()
  ));
  const reportFailure = useCallback((
    id: SteamPerformanceComponentId,
    control: SteamPerformanceComponent,
  ) => {
    setFailures((previous) => {
      if (previous.get(id) === control) return previous;
      const next = new Map(previous);
      next.set(id, control);
      return next;
    });
  }, []);
  const clearFailure = useCallback((
    id: SteamPerformanceComponentId,
    control: SteamPerformanceComponent,
  ) => {
    setFailures((previous) => {
      if (previous.get(id) !== control) return previous;
      const next = new Map(previous);
      next.delete(id);
      return next;
    });
  }, []);
  const available = surface.status === "ready";
  const partial = surface.rows.some(({ id, Component: Control }) => failures.get(id) === Control);
  const statusKey = !available
    ? surface.status === "loading"
      ? "steam.performance.loading"
      : "steam.performance.unavailable"
    : partial
      ? "steam.performance.partial"
      : "steam.performance.synced";
  const statusColor = partial
    ? theme.color.warn
    : available
      ? theme.color.ok
      : theme.color.textMuted;
  const renderRow = ({ id, Component: NativeControl }: SteamPerformanceRow) => (
    <NativeControlBoundary
      key={id}
      id={id}
      Control={NativeControl}
      onError={reportFailure}
      onRecovery={clearFailure}
    />
  );
  const reset = surface.rows.find(({ id }) => id === "reset");
  const resetFailed = Boolean(reset && failures.get(reset.id) === reset.Component);

  return (
    <Collapsible
      id="steam-performance"
      icon={<LuMonitorCog size={16} />}
      title={t("steam.performance.title")}
      summary={t(statusKey)}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.lg }}>
        <div
          role="status"
          aria-live="polite"
          style={{
            display: "flex",
            alignItems: "center",
            gap: theme.space.xs,
            color: statusColor,
            fontSize: theme.font.caption,
            lineHeight: 1.3,
          }}
        >
          {partial ? (
            <LuCircleAlert aria-hidden size={13} />
          ) : surface.status === "ready" ? (
            <LuCircleCheck aria-hidden size={13} />
          ) : surface.status === "loading" ? (
            <LuLoaderCircle aria-hidden size={13} />
          ) : (
            <LuCircleAlert aria-hidden size={13} />
          )}
          <span>{t(statusKey)}</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.lg }}>
          {GROUPS.map((group) => {
            const rows = surface.rows.filter(({ id }) => group.ids.has(id));
            return rows.length > 0 ? (
              <PerformanceGroup
                key={group.label}
                label={t(group.label)}
                rows={rows}
                hidden={rows.every(({ id, Component }) => failures.get(id) === Component)}
                renderRow={renderRow}
              />
            ) : null;
          })}

          {reset ? (
            <div
              data-pdc-steam-reset
              hidden={resetFailed}
              style={{
                display: resetFailed ? "none" : "block",
                paddingTop: theme.space.md,
                borderTop: `1px solid ${theme.color.hairline}`,
              }}
            >
              <style>{RESET_SEPARATOR_CSS}</style>
              {renderRow(reset)}
            </div>
          ) : null}
        </div>
      </div>
    </Collapsible>
  );
};
