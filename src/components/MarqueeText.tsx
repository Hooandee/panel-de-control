import { FC, useEffect, useRef } from "react";

/**
 * A label that gently scrolls back and forth ONLY when it's too wide for its box
 * (otherwise a plain static label — no wasted motion). Replaces the "Pot…"
 * ellipsis on the active tab with a readable ping-pong scroll.
 *
 * Cheap by design: one overflow measurement per text change, then a single
 * compositor-only transform animation via the Web Animations API — no per-frame
 * JS, no global stylesheet. The animation auto-cancels on unmount / text change.
 */
export const MarqueeText: FC<{ text: string }> = ({ text }) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const txtRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const box = boxRef.current;
    const txt = txtRef.current;
    if (!box || !txt) return;
    const amount = txt.scrollWidth - box.clientWidth;
    if (amount <= 2) return; // fits → stay still
    // Pause at each end so the start/end are readable; pace scales with distance.
    const anim = txt.animate(
      [
        { transform: "translateX(0)", offset: 0 },
        { transform: "translateX(0)", offset: 0.15 },
        { transform: `translateX(-${amount}px)`, offset: 0.5 },
        { transform: `translateX(-${amount}px)`, offset: 0.65 },
        { transform: "translateX(0)", offset: 1 },
      ],
      { duration: Math.max(4000, amount * 55 + 2500), iterations: Infinity, easing: "ease-in-out" },
    );
    return () => anim.cancel();
  }, [text]);

  return (
    <div ref={boxRef} style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
      <span ref={txtRef} style={{ display: "inline-block", whiteSpace: "nowrap" }}>
        {text}
      </span>
    </div>
  );
};
