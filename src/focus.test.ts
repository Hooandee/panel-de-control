import { describe, it, expect } from "vitest";
import { buildFocusCss, ensureFocusStyles, FOCUS_STYLE_ID, PDC_ROOT } from "./focus";

describe("buildFocusCss", () => {
  const css = buildFocusCss();

  it("targets Steam's live gpfocus class, scoped to our root", () => {
    expect(css).toContain(`.${PDC_ROOT} .gpfocus`);
  });

  it("colours the ring from the accent variable, with the blue default fallback", () => {
    expect(css).toContain("var(--pdc-accent-rgb");
    expect(css).toContain("78,161,255");
    expect(css).toContain("box-shadow");
  });

  it("rounds the ring so square controls don't get sharp corners", () => {
    expect(css).toContain("border-radius");
  });

  it("uses !important so it wins over the elements' inline box-shadow", () => {
    expect(css).toContain("!important");
  });
});

// Minimal document stub (no jsdom) — just the surface ensureFocusStyles touches.
function fakeDoc() {
  const store: Record<string, unknown> = {};
  const head = {
    children: [] as unknown[],
    appendChild(el: unknown) {
      this.children.push(el);
      const withId = el as { id?: string };
      if (withId.id) store[withId.id] = el;
    },
  };
  return {
    appended: () => head.children.length,
    doc: {
      getElementById: (id: string) => (store[id] as object) ?? null,
      createElement: (_tag: string) => ({ id: "", textContent: "" }),
      head,
    },
  };
}

describe("ensureFocusStyles", () => {
  it("injects the stylesheet once", () => {
    const { doc, appended } = fakeDoc();
    ensureFocusStyles(doc as unknown as Document);
    expect(appended()).toBe(1);
  });

  it("is idempotent — a second call adds nothing", () => {
    const { doc, appended } = fakeDoc();
    ensureFocusStyles(doc as unknown as Document);
    ensureFocusStyles(doc as unknown as Document);
    expect(appended()).toBe(1);
  });

  it("tags the injected element with the stable id", () => {
    const { doc } = fakeDoc();
    ensureFocusStyles(doc as unknown as Document);
    expect(doc.getElementById(FOCUS_STYLE_ID)).not.toBeNull();
  });

  it("never throws when the document surface is unusable", () => {
    expect(() => ensureFocusStyles({} as unknown as Document)).not.toThrow();
  });
});
