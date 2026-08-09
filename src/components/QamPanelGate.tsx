import {
  FC,
  PropsWithChildren,
  ReactNode,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

interface QamPanelCapabilities {
  ResizeObserver?: unknown;
  IntersectionObserver?: unknown;
}

interface QamPanelGateProps extends PropsWithChildren {
  lifecycle: AbortSignal;
  fallback?: ReactNode;
}

export function canGateQamPanel(host: QamPanelCapabilities = window): boolean {
  return typeof host.ResizeObserver === "function"
    && typeof host.IntersectionObserver === "function";
}

export const QamPanelGate: FC<QamPanelGateProps> = ({ children, lifecycle, fallback = null }) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<"hidden" | "content" | "fallback">("hidden");

  useLayoutEffect(() => {
    const host = hostRef.current;
    const doc = host?.ownerDocument;
    if (!host || !doc) {
      setMode("hidden");
      return;
    }

    let resize: ResizeObserver | null = null;
    let intersection: IntersectionObserver | null = null;
    let intersecting = false;
    let gated = false;
    let stopped = false;
    const refresh = () => {
      if (stopped) return;
      if (lifecycle.aborted || doc.visibilityState !== "visible") {
        setMode("hidden");
        return;
      }
      if (!gated) {
        setMode("fallback");
        return;
      }
      const rect = host.getBoundingClientRect();
      setMode(intersecting && rect.width > 0 && rect.height > 0 ? "content" : "hidden");
    };
    const disconnect = () => {
      intersection?.disconnect();
      resize?.disconnect();
      intersection = null;
      resize = null;
    };
    const teardown = (updateState: boolean) => {
      if (stopped) return;
      stopped = true;
      lifecycle.removeEventListener("abort", onAbort);
      doc.removeEventListener("visibilitychange", refresh);
      disconnect();
      if (updateState) setMode("hidden");
    };
    const onAbort = () => teardown(true);

    lifecycle.addEventListener("abort", onAbort);
    doc.addEventListener("visibilitychange", refresh);
    if (lifecycle.aborted) {
      teardown(true);
      return () => teardown(false);
    }

    const Resize = doc.defaultView?.ResizeObserver;
    const Intersection = doc.defaultView?.IntersectionObserver;
    if (!Resize || !Intersection) {
      refresh();
      return () => teardown(false);
    }

    try {
      resize = new Resize(refresh);
      intersection = new Intersection((entries) => {
        const entry = entries.find((candidate) => candidate.target === host);
        intersecting = !!entry?.isIntersecting && entry.intersectionRatio > 0;
        refresh();
      });
      gated = true;
      resize.observe(host);
      intersection.observe(host);
      refresh();
    } catch {
      disconnect();
      gated = false;
      refresh();
    }

    return () => teardown(false);
  }, [lifecycle]);

  return (
    <div ref={hostRef} data-testid="qam-panel-gate" style={{ minHeight: 1, width: "100%" }}>
      {mode === "content" ? children : mode === "fallback" ? fallback : null}
    </div>
  );
};
