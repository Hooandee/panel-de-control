import { useEffect, useRef } from "react";

const MARGINS = ["scroll-margin-block-start", "scroll-margin-block-end"] as const;

function preserveVisibleHalo(target: HTMLElement, view: Window) {
  for (let parent = target.parentElement; parent && parent !== target.ownerDocument.body; parent = parent.parentElement) {
    if (parent.scrollHeight <= parent.clientHeight || !/^(auto|scroll|hidden)$/.test(view.getComputedStyle(parent).overflowY)) continue;
    const bounds = parent.getBoundingClientRect();
    const scale = parent.offsetHeight > 0 ? bounds.height / parent.offsetHeight : 0;
    if (scale <= 0) continue;
    const control = target.getBoundingClientRect();
    const top = bounds.top + (parent.clientTop + 16) * scale;
    const bottom = bounds.top + (parent.clientTop + parent.clientHeight - 16) * scale;
    if (control.height > bottom - top) continue;
    const delta = control.top < top ? control.top - top : control.bottom > bottom ? control.bottom - bottom : 0;
    if (delta) parent.scrollTop += delta / scale;
  }
}

export function useCustomizeFocusVisibility() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = ref.current;
    const view = root?.ownerDocument.defaultView;
    if (!root || !view) return;
    let active = true;
    let frame: number | undefined;

    const onFocus = (event: FocusEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target || target.nodeType !== 1 || typeof target.scrollIntoView !== "function") return;
      if (frame !== undefined) view.cancelAnimationFrame(frame);
      frame = view.requestAnimationFrame(() => {
        frame = undefined;
        if (!active || !target.isConnected || !root.contains(target)
          || root.ownerDocument.activeElement !== target) return;

        const previous = MARGINS.map((property) => ({
          property,
          value: target.style.getPropertyValue(property),
          priority: target.style.getPropertyPriority(property),
        }));
        try {
          // Steam's initial scroll ignores the space painted by our focus halo.
          for (const property of MARGINS) target.style.setProperty(property, "16px", "important");
          target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
          // CEF can ignore scroll margins inside Steam's segmented controls.
          preserveVisibleHalo(target, view);
        } catch {
          // Keep Steam's native scrolling if this document cannot adjust it.
        } finally {
          for (const { property, value, priority } of previous) {
            if (value) target.style.setProperty(property, value, priority);
            else target.style.removeProperty(property);
          }
        }
      });
    };

    root.addEventListener("focusin", onFocus);
    return () => {
      active = false;
      root.removeEventListener("focusin", onFocus);
      if (frame !== undefined) view.cancelAnimationFrame(frame);
    };
  }, []);

  return ref;
}
