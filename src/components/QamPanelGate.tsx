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

// Ancestor overflow can suppress IntersectionObserver updates after vertical clipping.
const RETAINED_TAB_CHECK_MS = 100;

interface HorizontalBounds {
  left: number;
  right: number;
}

function overlapsHorizontally(rect: DOMRect, bounds: HorizontalBounds): boolean {
  return rect.left < bounds.right && rect.right > bounds.left;
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
    let fullyIntersecting = false;
    let retainedDuringScroll = false;
    let visibleHorizontalBounds: HorizontalBounds | null = null;
    let retentionPoll: number | null = null;
    let gated = false;
    let stopped = false;
    const stopRetentionPoll = () => {
      if (retentionPoll === null) return;
      doc.defaultView?.clearInterval(retentionPoll);
      retentionPoll = null;
    };
    const canRetainAtCurrentPosition = () => {
      const rect = host.getBoundingClientRect();
      return visibleHorizontalBounds !== null
        && rect.width > 0
        && rect.height > 0
        && overlapsHorizontally(rect, visibleHorizontalBounds);
    };
    const refresh = () => {
      if (stopped) return;
      if (lifecycle.aborted || doc.visibilityState !== "visible") {
        retainedDuringScroll = false;
        stopRetentionPoll();
        setMode("hidden");
        return;
      }
      if (!gated) {
        setMode("fallback");
        return;
      }
      const rect = host.getBoundingClientRect();
      setMode(
        (fullyIntersecting || retainedDuringScroll) && rect.width > 0 && rect.height > 0
          ? "content"
          : "hidden",
      );
    };
    const pollRetainedPosition = () => {
      const nextRetained = canRetainAtCurrentPosition();
      if (nextRetained === retainedDuringScroll) return;
      retainedDuringScroll = nextRetained;
      if (!nextRetained) stopRetentionPoll();
      refresh();
    };
    const startRetentionPoll = () => {
      const view = doc.defaultView;
      if (retentionPoll !== null || !view) return;
      retentionPoll = view.setInterval(pollRetainedPosition, RETAINED_TAB_CHECK_MS);
    };
    const disconnect = () => {
      intersection?.disconnect();
      resize?.disconnect();
      stopRetentionPoll();
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
      resize = new Resize(() => {
        if (retainedDuringScroll) {
          retainedDuringScroll = canRetainAtCurrentPosition();
          if (!retainedDuringScroll) stopRetentionPoll();
        }
        refresh();
      });
      intersection = new Intersection((entries) => {
        const entry = entries.find((candidate) => candidate.target === host);
        fullyIntersecting = !!entry?.isIntersecting && entry.intersectionRatio === 1;
        if (fullyIntersecting && entry) {
          retainedDuringScroll = false;
          visibleHorizontalBounds = {
            left: entry.boundingClientRect.left,
            right: entry.boundingClientRect.right,
          };
          stopRetentionPoll();
        } else {
          retainedDuringScroll = !!entry && canRetainAtCurrentPosition();
          if (retainedDuringScroll) startRetentionPoll();
          else stopRetentionPoll();
        }
        refresh();
      }, { threshold: [0, 1] });
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
