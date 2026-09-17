import { Component, type FC, useCallback, useState } from "react";
import { LuMonitorCog } from "react-icons/lu";

import { useI18n } from "../i18n";
import type {
  SteamPerformanceComponent,
  SteamPerformanceComponentId,
} from "../steam/performanceSurface";
import { useSteamPerformanceSurface } from "../steam/useSteamPerformanceSurface";
import { theme } from "../theme";
import { Collapsible } from "./Collapsible";

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

export const SteamPerformanceCard: FC = () => {
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
  const partial = surface.rows.some(({ id, Component: Control }) => (
    failures.get(id) === Control
  ));
  const status = t(!available
    ? "steam.performance.unavailable"
    : partial
      ? "steam.performance.partial"
      : "steam.performance.synced");

  return (
    <Collapsible
      id="steam-performance"
      icon={<LuMonitorCog size={16} />}
      title={t("steam.performance.title")}
      summary={status}
    >
      <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.4 }}>
        {t("steam.performance.desc")}
      </div>
      <div
        style={{
          color: partial ? theme.color.warn : available ? theme.color.accent : theme.color.textMuted,
          fontSize: theme.font.caption,
          marginTop: theme.space.xs,
          marginBottom: available ? theme.space.xs : 0,
        }}
      >
        {status}
      </div>
      {surface.rows.map(({ id, Component: NativeControl }) => (
        <NativeControlBoundary
          key={id}
          id={id}
          Control={NativeControl}
          onError={reportFailure}
          onRecovery={clearFailure}
        />
      ))}
    </Collapsible>
  );
};
