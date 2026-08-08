// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", async () => {
  const { createElement } = await import("react");
  return {
    Focusable: ({
      children,
      onActivate: _onActivate,
      onClick,
      ...props
    }: {
      children?: ReactNode;
      onActivate?: () => void;
      onClick?: () => void;
      [key: string]: unknown;
    }) => {
      const interactive = Boolean(onClick || _onActivate);
      return createElement(
        interactive ? "button" : "div",
        { ...props, ...(interactive ? { type: "button" } : {}), onClick },
        children,
      );
    },
  };
});

vi.mock("../api", () => ({
  getUiPrefs: vi.fn(async () => ({})),
  setUiPrefs: vi.fn(async () => true),
}));

import { LanguageToggle } from "../components/LanguageToggle";
import * as i18n from "./index";

const DICTS = i18n.DICTS;
const STORAGE_KEY = "panel-de-control-lang";
const PLACEHOLDER = /\{\w+\}/g;

function italianCatalog(): Record<string, string> {
  return DICTS.it;
}

function placeholders(value: string): string[] {
  return [...(value.match(PLACEHOLDER) ?? [])].sort();
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("Italian catalog", () => {
  it("has exactly the same keys as the Spanish catalog", () => {
    const italian = italianCatalog();

    expect(Object.keys(italian).sort()).toEqual(Object.keys(DICTS.es).sort());
  });

  it("preserves every interpolation placeholder", () => {
    const italian = italianCatalog();
    const spanish = DICTS.es;

    for (const key of Object.keys(spanish)) {
      expect(placeholders(italian[key] ?? ""), key).toEqual(placeholders(spanish[key]));
    }
  });

  it("does not use em dashes", () => {
    expect(Object.values(italianCatalog()).some((value) => value.includes("—"))).toBe(false);
  });

  it("keeps established technical and product terms", () => {
    const values = Object.values(italianCatalog());
    const terms = [
      "TDP",
      "Auto-TDP",
      "FPS",
      "CPU",
      "GPU",
      "HDR",
      "RGB",
      "FSR",
      "XeSS",
      "RDNA",
      "Proton",
      "SteamOS",
      "Decky",
      "MangoHud",
      "GameMode",
      "PowerStation",
      "SimpleDeckyTDP",
      "Colores",
    ];

    for (const term of terms) {
      expect(values.some((value) => value.includes(term)), term).toBe(true);
    }
  });

  it("uses the Italian product title and an Italian Auto-TDP label", () => {
    const italian = italianCatalog();

    expect(italian["app.title"]).toBe("Pannello di controllo");
    expect(italian["tdp.auto.title"]).toContain("TDP");
    expect(italian["lang.italian"]).toBe("Italiano");
  });

  it("accepts a persisted Italian selection for lookup", () => {
    window.localStorage.setItem(STORAGE_KEY, "it");

    expect(i18n.translate("app.title")).toBe("Pannello di controllo");
  });
});

describe("LanguageToggle", () => {
  it("persists Italian when its localized selector button is pressed", () => {
    render(
      createElement(
        i18n.I18nProvider,
        null,
        createElement(LanguageToggle),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Italiano" }));

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("it");
  });
});
