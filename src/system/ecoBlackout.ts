import { findSP } from "@decky/ui";
import { getQamDocument } from "../qamDocument";

const ID = "pdc-eco-blackout";

// Steam's main window and the QAM are separate documents; the layer covers both.
function steamDocuments(): Document[] {
  const docs = [findSP()?.document, getQamDocument()];
  return docs.filter((doc, i): doc is Document => !!doc?.body && docs.indexOf(doc) === i);
}

// Black layer over Steam's UI: the fallback for panels gamescope cannot switch off, and the
// catch for the tap that wakes a sleeping panel, so it never lands on a control underneath.
export function showBlackout(onTap?: () => void, docs: Document[] = steamDocuments()): boolean {
  for (const doc of docs) {
    if (doc.getElementById(ID)) continue;
    const layer = doc.createElement("div");
    layer.id = ID;
    layer.style.cssText = "position:fixed;inset:0;background:#000;z-index:2147483647;cursor:none";
    if (onTap) layer.addEventListener("pointerdown", onTap);
    doc.body.appendChild(layer);
  }
  return docs.length > 0;
}

export function hideBlackout(docs: Document[] = steamDocuments()): void {
  for (const doc of docs) doc.getElementById(ID)?.remove();
}
