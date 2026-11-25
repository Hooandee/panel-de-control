import { findSP, quickAccessMenuClasses } from "@decky/ui";
import { getQamDocument } from "../qamDocument";

const ID = "pdc-eco-countdown";
const RING = 2 * Math.PI * 9;

// The QAM is its own window over Steam's, and its size and offset differ per handheld (on
// some it runs past the screen edge): centre on its visible content when it is open.
function target(): [Document | null, string] {
  const qam = getQamDocument();
  const view = qam?.defaultView;
  const menu = qam?.querySelector(`.${quickAccessMenuClasses?.Menu}`)?.getBoundingClientRect();
  if (!qam || !view || !menu?.width || qam.visibilityState !== "visible" || !qam.hasFocus()) {
    return [findSP()?.document ?? null, "left:50%;bottom:88px"];
  }
  const tabs = qam.querySelector(`.${quickAccessMenuClasses?.Tabs}`)?.getBoundingClientRect();
  const left = Math.max(menu.left, tabs?.right ?? menu.left);
  const right = Math.min(menu.right, view.screen.width - view.screenX);
  return [qam, `left:${Math.round((left + right) / 2)}px;bottom:24px`];
}

// Pill counting down to the screen going dark; returns its cancel. Steam's UI is not drawn
// over a running game, so there it simply isn't seen.
export function startCountdown(seconds: number, label: string, onDone: () => void): () => void {
  const [doc, place] = target();
  doc?.getElementById(ID)?.remove();
  const pill = doc?.createElement("div");
  if (doc && pill) {
    pill.id = ID;
    pill.style.cssText = `position:fixed;${place};transform:translateX(-50%);z-index:2147483646;
      display:flex;align-items:center;gap:10px;padding:7px 8px 7px 16px;border-radius:999px;
      background:rgba(14,20,27,.92);box-shadow:0 8px 28px rgba(0,0,0,.45),inset 0 0 0 1px rgba(255,255,255,.08);
      color:#dfe3ea;font:500 14px 'Motiva Sans',Arial,sans-serif;pointer-events:none`;
    pill.innerHTML = `<span></span><svg width="26" height="26" viewBox="0 0 26 26">
      <circle cx="13" cy="13" r="9" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="2.5"/>
      <circle cx="13" cy="13" r="9" fill="none" stroke="#59bf40" stroke-width="2.5" stroke-linecap="round"
        stroke-dasharray="${RING}" transform="rotate(-90 13 13)"/>
      <text x="13" y="17.5" text-anchor="middle" fill="#fff" style="font:600 12px 'Motiva Sans',Arial,sans-serif">${seconds}</text></svg>`;
    pill.querySelector("span")!.textContent = label;
    doc.body.appendChild(pill);
    // Web Animations start from the first frame on every insertion; a CSS transition set
    // right after appending can be coalesced into its end state and never play.
    pill.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: "ease-out" });
    pill.querySelectorAll("circle")[1].animate([{ strokeDashoffset: 0 }, { strokeDashoffset: RING }], {
      duration: seconds * 1000,
      fill: "forwards",
    });
  }
  let left = seconds;
  const tick = setInterval(() => {
    left -= 1;
    const digit = pill?.querySelector("text");
    if (left > 0 && digit) digit.textContent = String(left);
    if (left > 0) return;
    clearInterval(tick);
    pill?.remove();
    onDone();
  }, 1000);
  return () => {
    clearInterval(tick);
    pill?.remove();
  };
}
