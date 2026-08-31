// @vitest-environment happy-dom
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ setLang: vi.fn() }));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, ...props }: { children?: ReactNode; onActivate?: () => void } & Record<string, unknown>) => (
    <div {...props} onClick={onActivate}>{children}</div>
  ),
}));
vi.mock("../i18n", () => ({
  useI18n: () => ({ lang: "en", setLang: mocks.setLang, t: (key: string) => key }),
}));

import { LanguageToggle } from "./LanguageToggle";

describe("LanguageToggle", () => {
  it("offers Italian as a selectable language", () => {
    render(<LanguageToggle />);

    fireEvent.click(screen.getByLabelText("lang.italian"));

    expect(mocks.setLang).toHaveBeenCalledWith("it");
  });
});
