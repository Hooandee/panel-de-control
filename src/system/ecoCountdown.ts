import { findSP } from "@decky/ui";
import { getQamDocument } from "../qamDocument";

const ID = "pdc-eco-countdown";
const RING_R = 9;
const RING_LEN = 2 * Math.PI * RING_R;

export interface Countdown {
  cancel: () => void;
}

// The QAM is its own window over Steam's; while it is open the pill belongs there.
function visibleDocument(): Document | null {
  const qam = getQamDocument();
  if (qam && qam.visibilityState === "visible" && qam.hasFocus()) return qam;
  return findSP()?.document ?? null;
}

// The QAM window extends past the right edge of the screen; centre on its visible panel.
function placement(doc: Document): string {
  if (doc !== getQamDocument()) return "left:50%;bottom:88px";
  const view = doc.defaultView;
  if (!view) return "left:50%;bottom:24px";
  const right = Math.min(view.innerWidth, view.screen.width - view.screenX);
  const panelLeft = doc.querySelector(".Panel")?.getBoundingClientRect().left ?? 0;
  return `left:${Math.round((panelLeft + right) / 2)}px;bottom:24px`;
}

// Small pill over Steam's UI counting down to the screen going dark; `onDone` runs when it
// reaches zero. Steam's UI is not drawn over a running game, so there it simply isn't seen.
export function startCountdown(
  seconds: number,
  label: string,
  onDone: () => void,
  doc: Document | null = visibleDocument(),
): Countdown {
  doc?.getElementById(ID)?.remove();
  let pill: HTMLElement | null = null;
  let digit: Element | null = null;
  if (doc?.body) {
    pill = doc.createElement("div");
    pill.id = ID;
    pill.style.cssText = [
      "position:fixed", placement(doc), "z-index:2147483646",
      "display:flex", "align-items:center", "gap:10px", "padding:7px 16px 7px 8px",
      "border-radius:999px", "background:rgba(14,20,27,0.92)",
      "box-shadow:0 8px 28px rgba(0,0,0,0.45),inset 0 0 0 1px rgba(255,255,255,0.08)",
      "color:#dfe3ea", "font:500 14px 'Motiva Sans',Arial,sans-serif", "letter-spacing:0.01em",
      "pointer-events:none", "transform:translate(-50%,0)",
    ].join(";");
    pill.innerHTML =
      `<svg width="26" height="26" viewBox="0 0 26 26" style="display:block">` +
      `<circle cx="13" cy="13" r="${RING_R}" fill="none" stroke="rgba(255,255,255,0.14)" stroke-width="2.5"/>` +
      `<circle cx="13" cy="13" r="${RING_R}" fill="none" stroke="#59bf40" stroke-width="2.5" stroke-linecap="round"` +
      ` stroke-dasharray="${RING_LEN}" stroke-dashoffset="0" transform="rotate(-90 13 13)"/>` +
      `<text x="13" y="17.5" text-anchor="middle" fill="#ffffff" style="font:600 12px 'Motiva Sans',Arial,sans-serif">${seconds}</text>` +
      `</svg><span></span>`;
    pill.querySelector("span")!.textContent = label;
    digit = pill.querySelector("text");
    doc.body.appendChild(pill);
    // Web Animations start from the first frame on every insertion; a CSS transition set
    // right after appending can be coalesced into the final state and never play.
    pill.animate(
      [{ opacity: 0, transform: "translate(-50%,8px)" }, { opacity: 1, transform: "translate(-50%,0)" }],
      { duration: 180, easing: "ease-out" },
    );
    pill.querySelectorAll("circle")[1].animate(
      [{ strokeDashoffset: 0 }, { strokeDashoffset: RING_LEN }],
      { duration: seconds * 1000, easing: "linear", fill: "forwards" },
    );
  }

  let left = seconds;
  const tick = setInterval(() => {
    left -= 1;
    if (left > 0) {
      if (digit) digit.textContent = String(left);
      return;
    }
    clearInterval(tick);
    pill?.remove();
    onDone();
  }, 1000);

  return {
    cancel: () => {
      clearInterval(tick);
      if (!pill) return;
      const leaving = pill;
      leaving
        .animate(
          [{ opacity: 1, transform: "translate(-50%,0)" }, { opacity: 0, transform: "translate(-50%,8px)" }],
          { duration: 160, easing: "ease-in", fill: "forwards" },
        )
        .finished.then(() => leaving.remove(), () => leaving.remove());
    },
  };
}
