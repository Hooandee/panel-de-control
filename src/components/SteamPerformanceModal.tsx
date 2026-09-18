import { Component, type FC, type ReactNode, useCallback, useState } from "react";
import { Focusable, ModalRoot } from "@decky/ui";
import { LuMonitorCog } from "react-icons/lu";

import { useI18n } from "../i18n";
import type {
  SteamPerformanceComponent,
  SteamPerformanceComponentId,
  SteamPerformanceRow,
} from "../steam/performanceSurface";
import { useSteamPerformanceSurface } from "../steam/useSteamPerformanceSurface";
import { theme } from "../theme";
import { CompactBackAction } from "./CompactBackAction";
import { FocusRoot } from "./FocusRoot";

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
    const { Control } = this.props;
    return <Control />;
  }
}

const GROUPS: ReadonlyArray<{
  label: string;
  ids: ReadonlySet<SteamPerformanceComponentId>;
}> = [
  {
    label: "steam.performance.group.display",
    ids: new Set(["profile", "legacyFrameRate", "appFrameRate", "disableFrameLimit", "refreshRate"]),
  },
  {
    label: "steam.performance.group.fluidity",
    ids: new Set(["variableResolution", "vrr", "allowTearing"]),
  },
  {
    label: "steam.performance.group.scaling",
    ids: new Set([
      "combinedScaling",
      "splitScalingFilter",
      "scalingMode",
      "sharpness",
      "fsrSharpness",
      "nisSharpness",
    ]),
  },
];

interface PerformanceGroupProps {
  label: string;
  rows: SteamPerformanceRow[];
  renderRow: (row: SteamPerformanceRow) => ReactNode;
}

const PerformanceGroup: FC<PerformanceGroupProps> = ({ label, rows, renderRow }) => (
  <section role="group" aria-label={label} style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
    <div style={theme.sectionLabel}>{label}</div>
    <div style={{
      ...theme.card,
      display: "flex",
      flexDirection: "column",
      gap: theme.space.sm,
      padding: theme.space.lg,
      overflow: "hidden",
    }}>
      {rows.map(renderRow)}
    </div>
  </section>
);

export const SteamPerformanceModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => {
  const { t } = useI18n();
  const surface = useSteamPerformanceSurface();
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
  const status = t(!available
    ? "steam.performance.unavailable"
    : partial
      ? "steam.performance.partial"
      : "steam.performance.synced");
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

  return (
    <ModalRoot
      closeModal={closeModal}
      bAllowFullSize
      onCancel={closeModal}
      onEscKeypress={closeModal}
    >
      <FocusRoot style={{ minHeight: "100%" }}>
        <Focusable noFocusRing style={{ minHeight: "100%", width: "100%" }}>
          <main style={{
            width: "100%",
            maxWidth: 660,
            margin: "0 auto",
            padding: "8px 10px 48px",
            color: theme.color.textPrimary,
          }}>
            <CompactBackAction onBack={() => closeModal?.()} />

            <header style={{
              display: "flex",
              alignItems: "flex-start",
              gap: theme.space.md,
              margin: `${theme.space.md}px 0 ${theme.space.lg}px`,
            }}>
              <span aria-hidden style={{
                width: 44,
                height: 44,
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: theme.radius.sm,
                color: theme.color.accent,
                background: `rgba(${theme.color.accentRgb},0.12)`,
                boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.22)`,
              }}>
                <LuMonitorCog size={22} />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h2 style={{ margin: 0, fontSize: 28, lineHeight: 1.1, letterSpacing: -0.5 }}>
                  {t("steam.performance.detailTitle")}
                </h2>
                <div style={{
                  marginTop: theme.space.xs,
                  color: theme.color.textMuted,
                  fontSize: theme.font.body,
                  lineHeight: 1.45,
                }}>
                  {t("steam.performance.desc")}
                </div>
                <div style={{
                  marginTop: theme.space.sm,
                  color: partial ? theme.color.warn : available ? theme.color.ok : theme.color.textMuted,
                  fontSize: theme.font.caption,
                }}>
                  {status}
                </div>
              </div>
            </header>

            <div style={{ display: "flex", flexDirection: "column", gap: theme.space.lg }}>
              {GROUPS.map((group) => {
                const rows = surface.rows.filter(({ id }) => group.ids.has(id));
                return rows.length > 0 ? (
                  <PerformanceGroup
                    key={group.label}
                    label={t(group.label)}
                    rows={rows}
                    renderRow={renderRow}
                  />
                ) : null;
              })}

              {reset ? (
                <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden" }}>
                  {renderRow(reset)}
                </div>
              ) : null}
            </div>
          </main>
        </Focusable>
      </FocusRoot>
    </ModalRoot>
  );
};
