export type ConstellationScene = "direct" | "orbit" | "constellation";

export interface ConstellationFocus {
  moveTo(card: Element): void;
  clear(): void;
  dispose(): void;
}

function sameVisualRow(origin: Element, candidate: Element): boolean {
  if (origin.getAttribute("role") !== candidate.getAttribute("role")) return false;
  const originRect = origin.getBoundingClientRect();
  const candidateRect = candidate.getBoundingClientRect();
  if (originRect.height <= 0 || candidateRect.height <= 0) return true;
  const originCenter = originRect.top + originRect.height / 2;
  const candidateCenter = candidateRect.top + candidateRect.height / 2;
  return Math.abs(originCenter - candidateCenter) <= Math.max(originRect.height, candidateRect.height) / 2;
}

export function startConstellationFocus(scene: ConstellationScene): ConstellationFocus {
  const marked: Element[] = [];
  let disposed = false;
  const clear = () => {
    for (const card of marked.splice(0)) card.removeAttribute("data-pdc-obsidian-distance");
  };

  return {
    moveTo(card) {
      if (disposed) return;
      clear();
      card.setAttribute("data-pdc-obsidian-distance", "0");
      marked.push(card);
      const distance = scene === "constellation" ? 2 : scene === "orbit" ? 1 : 0;
      let previous = card.previousElementSibling;
      let next = card.nextElementSibling;
      for (let step = 1; step <= distance; step += 1) {
        if (previous && sameVisualRow(card, previous)) {
          previous.setAttribute("data-pdc-obsidian-distance", String(-step));
          marked.push(previous);
          previous = previous.previousElementSibling;
        } else {
          previous = null;
        }
        if (next && sameVisualRow(card, next)) {
          next.setAttribute("data-pdc-obsidian-distance", String(step));
          marked.push(next);
          next = next.nextElementSibling;
        } else {
          next = null;
        }
      }
    },
    clear,
    dispose() {
      if (disposed) return;
      disposed = true;
      clear();
    },
  };
}
