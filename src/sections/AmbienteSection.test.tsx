// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div> }));
vi.mock("../assets/ambient-preview.jpg", () => ({ default: "ambient-preview.jpg" }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

import { AmbienteSection } from "./AmbienteSection";

describe("AmbienteSection", () => {
  afterEach(cleanup);

  it("announces Ambient as coming soon with its preview", () => {
    render(<AmbienteSection />);

    expect(screen.getByText("ambient.soon.title")).toBeTruthy();
    expect(screen.getByText("ambient.soon.body")).toBeTruthy();
    expect(screen.getByText("comingSoon.badge")).toBeTruthy();
    expect(screen.getByRole("img", { name: "ambient.soon.imageAlt" }).getAttribute("src")).toBe("ambient-preview.jpg");
  });
});
