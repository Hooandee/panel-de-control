// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCAL_THEME_CATALOG } from "../themes/catalog";
import type { ThemeCardModel } from "../themes/state";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, onClick, ...props }: {
    children?: ReactNode;
    onActivate?: () => void;
    onClick?: () => void;
  } & Record<string, unknown>) => (
    <div {...props} onClick={() => { onActivate?.(); onClick?.(); }}>{children}</div>
  ),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

import { ThemeCard } from "./ThemeCard";

describe("ThemeCard", () => {
  afterEach(cleanup);

  it("shows an available update even while the theme is active", () => {
    const card: ThemeCardModel = {
      id: "hooandee-gallery",
      catalog: LOCAL_THEME_CATALOG.themes[0],
      installed: true,
      active: true,
      installedVersion: "0.5.0",
      preferredInstallSource: "bundled",
      versionRelation: "update-available",
      updateAvailable: true,
    };

    render(<ThemeCard card={card} operation={null} onOpen={vi.fn()} />);

    expect(screen.getByText("themes.state.updateAvailable")).toBeTruthy();
    expect(screen.getByText("themes.state.active")).toBeTruthy();
    expect(screen.getByRole("button", {
      name: `themes.gallery.name themes.state.active`,
    }).getAttribute("aria-describedby")).toBe(`theme-card-${card.id}-description`);
    const surface = screen.getByRole("button");
    expect(surface.getAttribute("data-pdc-focus-radius")).toBe("true");
    expect(surface.style.getPropertyValue("--pdc-focus-radius")).toBe("14px");
  });

  it("shows the official published version without replacing local state", () => {
    const card: ThemeCardModel = {
      id: "hooandee-gallery",
      catalog: LOCAL_THEME_CATALOG.themes[0],
      installed: true,
      active: true,
      installedVersion: "0.7.8",
      publishedVersion: "0.7.9",
      publicationCompatibility: "compatible",
      targetVersion: "0.7.9",
      preferredInstallSource: "official-remote",
      versionRelation: "update-available",
      updateAvailable: true,
    };

    render(<ThemeCard card={card} operation={null} onOpen={vi.fn()} />);

    expect(screen.getByText("themes.state.active")).toBeTruthy();
    expect(screen.getByText("themes.remote.card.available")).toBeTruthy();
    expect(screen.getByText("themes.state.updateAvailable")).toBeTruthy();
  });

  it("opens once when Decky reports activate and click for the same action", async () => {
    const onOpen = vi.fn();
    const card: ThemeCardModel = {
      id: "hooandee-gallery",
      catalog: LOCAL_THEME_CATALOG.themes[0],
      installed: true,
      active: false,
      preferredInstallSource: "bundled",
      versionRelation: "current",
      updateAvailable: false,
    };
    const rendered = render(<ThemeCard card={card} operation={null} onOpen={onOpen} />);
    const button = rendered.container.querySelector<HTMLElement>('[role="button"]');
    if (!button) throw new Error("Theme card button was not rendered");

    fireEvent.click(button);
    expect(onOpen).toHaveBeenCalledOnce();

    await Promise.resolve();
    fireEvent.click(button);
    expect(onOpen).toHaveBeenCalledTimes(2);
  });

  it("renders coming-soon themes as non-interactive localized cards", () => {
    const onOpen = vi.fn();
    const card: ThemeCardModel = {
      id: "hooandee-shattered-realms",
      catalog: LOCAL_THEME_CATALOG.themes[1],
      installed: true,
      active: true,
      installedVersion: "0.4.0",
      preferredInstallSource: null,
      versionRelation: "unknown",
      updateAvailable: false,
    };

    render(<ThemeCard card={card} operation={null} onOpen={onOpen} />);

    const surface = screen.getByTestId("theme-card-hooandee-shattered-realms");
    expect(surface.getAttribute("aria-disabled")).toBe("true");
    expect(surface.getAttribute("role")).toBe("group");
    expect(surface.hasAttribute("data-pdc-focus-radius")).toBe(false);
    expect(surface.style.getPropertyValue("--pdc-focus-radius")).toBe("");
    expect(screen.getByText("themes.shattered.name")).toBeTruthy();
    expect(screen.getByText("themes.state.comingSoon")).toBeTruthy();
    fireEvent.click(surface);
    expect(onOpen).not.toHaveBeenCalled();
  });
});
