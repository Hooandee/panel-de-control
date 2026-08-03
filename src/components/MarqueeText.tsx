import { CSSProperties, FC, useEffect, useRef } from "react";

interface MarqueeTextProps {
  text: string;
  alignWhenFits?: CSSProperties["textAlign"];
}

export const MarqueeText: FC<MarqueeTextProps> = ({ text, alignWhenFits = "left" }) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const txtRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const box = boxRef.current;
    const txt = txtRef.current;
    if (!box || !txt) return;
    const motion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)");
    let animation: Animation | null = null;

    const reconcile = () => {
      animation?.cancel();
      animation = null;

      const amount = txt.scrollWidth - box.clientWidth;
      const overflowing = amount > 2;
      const staticOverflow = overflowing && Boolean(motion?.matches);
      box.style.textAlign = overflowing ? "left" : alignWhenFits;
      txt.style.maxWidth = staticOverflow ? "100%" : "";
      txt.style.overflow = staticOverflow ? "hidden" : "";
      txt.style.textOverflow = staticOverflow ? "ellipsis" : "";

      if (!overflowing || staticOverflow) return;
      animation = txt.animate(
        [
          { transform: "translateX(0)", offset: 0 },
          { transform: "translateX(0)", offset: 0.15 },
          { transform: `translateX(-${amount}px)`, offset: 0.5 },
          { transform: `translateX(-${amount}px)`, offset: 0.65 },
          { transform: "translateX(0)", offset: 1 },
        ],
        { duration: Math.max(4000, amount * 55 + 2500), iterations: Infinity, easing: "ease-in-out" },
      );
    };

    reconcile();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(reconcile);
    observer?.observe(box);
    observer?.observe(txt);
    motion?.addEventListener?.("change", reconcile);
    return () => {
      observer?.disconnect();
      motion?.removeEventListener?.("change", reconcile);
      animation?.cancel();
    };
  }, [alignWhenFits, text]);

  return (
    <div ref={boxRef} style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
      <span ref={txtRef} style={{ display: "inline-block", whiteSpace: "nowrap" }}>
        {text}
      </span>
    </div>
  );
};
