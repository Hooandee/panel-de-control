// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ThemeCardModel } from "../themes/state";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, ...props }: { children?: ReactNode; onActivate?: () => void } & HTMLAttributes<HTMLDivElement>) => (
    <div onClick={onActivate} {...props}>{children}</div>
  ),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ lang: "en", t: (key: string) => key }) }));

import { ThemeCard } from "./ThemeCard";

function card(overrides: Partial<ThemeCardModel> = {}): ThemeCardModel {
  return {
    id: "example-theme",
    release: {
      catalogId: "example-theme", cssLoaderName: "Example Theme", publishedVersion: "1.2.3",
      displayName: { es: "Tema", en: "Example Theme", it: "Tema" },
      description: { es: "Descripcion", en: "Description", it: "Descrizione" },
      author: "Example Author", tags: ["dark"], notes: {}, compatibility: "compatible",
    },
    installed: false,
    active: false,
    targetVersion: "1.2.3",
    installable: true,
    versionRelation: "not-installed",
    updateAvailable: false,
    ...overrides,
  };
}

describe("ThemeCard", () => {
  afterEach(cleanup);

  it("renders published presentation as text with one neutral preview", () => {
    render(<ThemeCard card={card({
      release: {
        ...card().release,
        displayName: { es: "Tema", en: "<img src=x onerror=alert(1)>", it: "Tema" },
      },
    })} operation={null} onOpen={vi.fn()} />);

    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByTestId("theme-preview").getAttribute("data-theme-id")).toBeNull();
  });

  it("remains browsable when incompatible", () => {
    const onOpen = vi.fn();
    render(<ThemeCard card={card({
      installable: false,
      targetVersion: undefined,
      release: { ...card().release, compatibility: "incompatible-panel" },
    })} operation={null} onOpen={onOpen} />);

    fireEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledOnce();
    expect(screen.getByText("themes.remote.card.incompatible")).toBeTruthy();
  });

  it("announces installed, active and update state from CSS Loader truth", () => {
    render(<ThemeCard card={card({
      installed: true, active: true, installedVersion: "1.2.2",
      versionRelation: "update-available", updateAvailable: true,
    })} operation={null} onOpen={vi.fn()} />);

    expect(screen.getByText("themes.state.active")).toBeTruthy();
    expect(screen.getByText("themes.state.updateAvailable")).toBeTruthy();
  });

  it("deduplicates Decky activate/click delivery within one microtask", async () => {
    const onOpen = vi.fn();
    render(<ThemeCard card={card()} operation={null} onOpen={onOpen} />);
    const button = screen.getByRole("button");

    fireEvent.click(button);
    fireEvent.click(button);
    expect(onOpen).toHaveBeenCalledOnce();
    await Promise.resolve();
    fireEvent.click(button);
    expect(onOpen).toHaveBeenCalledTimes(2);
  });
});
