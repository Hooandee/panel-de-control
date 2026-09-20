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
    expect(css).toContain("border-radius: var(--pdc-focus-radius, 10px) !important");
  });

  it("lets explicit QAM surfaces override higher-specificity theme focus radii", () => {
    expect(css).toContain(
      `html:root #QuickAccess-Menu .${PDC_ROOT} [data-pdc-focus-radius].gpfocus`,
    );
  });

  it("uses !important so it wins over the elements' inline box-shadow", () => {
    expect(css).toContain("!important");
  });

  it("compacts Decky's HUD slider chrome and removes its fixed minimum width", () => {
    expect(css).toContain(".pdc-hud-slider");
    expect(css).toContain("margin-inline: 0 !important");
    expect(css).toContain("padding-block: 6px !important");
    expect(css).toContain(".pdc-hud-slider > div > div");
    expect(css).toContain("min-width: 0 !important");
    expect(css).toContain("width: 100% !important");
  });

  it("retains the nested-card override for Decky's fixed slider width", () => {
    expect(css).toContain(`.${PDC_ROOT} .pdc-contained-slider`);
    expect(css).toContain(`.${PDC_ROOT} .pdc-contained-slider > div > div`);
    expect(css).toContain("margin-inline: 0 !important");
    expect(css).toContain("min-width: 0 !important");
    expect(css).toContain("width: 100% !important");
  });

  it("replaces Steam's Dashboard gradient with the section colour and restrained motion", () => {
    expect(css).toContain(".pdc-dashboard-card-focused");
    expect(css).toContain(
      `html:root #QuickAccess-Menu .${PDC_ROOT} .pdc-dashboard-card-focused`,
    );
    expect(css).toContain("background: transparent !important");
    expect(css).toContain("background-image: none !important");
    expect(css).toContain(".pdc-dashboard-card-surface");
    expect(css).toContain("var(--pdc-card-accent)");
    expect(css).not.toContain("translateY(-2px)");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
  });
});

// Minimal document stub (no jsdom) — just the surface ensureFocusStyles touches.
function fakeDoc(existingText?: string) {
  const store: Record<string, unknown> = {};
  const head = {
    children: [] as unknown[],
    appendChild(el: unknown) {
      this.children.push(el);
      const withId = el as { id?: string };
      if (withId.id) store[withId.id] = el;
    },
  };
  if (existingText !== undefined) {
    const existing = { id: FOCUS_STYLE_ID, textContent: existingText };
    head.children.push(existing);
    store[FOCUS_STYLE_ID] = existing;
  }
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

  it("refreshes a surviving stylesheet after a plugin upgrade", () => {
    const { doc, appended } = fakeDoc("stale focus css");

    ensureFocusStyles(doc as unknown as Document);

    expect(appended()).toBe(1);
    expect((doc.getElementById(FOCUS_STYLE_ID) as { textContent: string }).textContent).toBe(buildFocusCss());
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
