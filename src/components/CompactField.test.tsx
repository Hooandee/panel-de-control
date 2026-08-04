// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Dropdown: ({ rgOptions, selectedOption, onChange, renderButtonValue, disabled, menuLabel }: any) => {
    const selected = rgOptions.find((option: any) => option.data === selectedOption);
    const next = rgOptions.find((option: any) => option.data !== selectedOption);
    return (
      <button
        aria-label={menuLabel}
        disabled={disabled}
        onClick={() => onChange?.(next ?? selected)}
      >
        {renderButtonValue?.(selected?.label) ?? selected?.label}
      </button>
    );
  },
}));

import { CompactChoiceField, CompactFieldSurface, InlineNotice } from "./CompactField";

afterEach(cleanup);

describe("CompactField", () => {
  it("keeps one compact padding layer without clipping focused controls", () => {
    render(<CompactFieldSurface>Control</CompactFieldSurface>);

    const surface = screen.getByTestId("compact-field-surface");
    expect(surface.style.boxSizing).toBe("border-box");
    expect(surface.style.minWidth).toBe("0");
    expect(surface.style.padding).toBe("8px");
    expect(surface.style.overflow).not.toBe("hidden");
  });

  it("wraps a long label and ellipsizes the selected value inside the QAM width", () => {
    render(
      <CompactChoiceField
        label="Patrón del mando derecho con un texto largo"
        options={[{ data: "racing", label: "Carreras con un valor largo" }]}
        value="racing"
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId("compact-field-label").style.overflowWrap).toBe("anywhere");
    const value = screen.getByTestId("compact-field-value");
    expect(value.style.minWidth).toBe("0");
    expect(value.style.overflow).toBe("hidden");
    expect(value.style.textOverflow).toBe("ellipsis");
    expect(value.style.whiteSpace).toBe("nowrap");
    const control = screen.getByTestId("compact-field-control");
    expect(control.style.width).toBe("100%");
    expect(control.style.maxWidth).toBe("100%");
    expect(control.style.minWidth).toBe("0");
    expect(screen.getByRole("button", { name: "Patrón del mando derecho con un texto largo" }))
      .toBeTruthy();
  });

  it("does not emit a mutation when Decky returns the current option", () => {
    const onChange = vi.fn();
    render(
      <CompactChoiceField
        label="Motor"
        options={[{ data: "both", label: "Ambos" }]}
        value="both"
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps the QAM scroll position when a dropdown selection updates", async () => {
    const Field = () => {
      const [value, setValue] = useState("soft");
      return (
        <CompactChoiceField
          label="Patrón"
          options={[
            { data: "soft", label: "Suave" },
            { data: "hard", label: "Fuerte" },
          ]}
          value={value}
          onChange={(next) => {
            const host = screen.getByTestId("scroll-host");
            setValue(next);
            requestAnimationFrame(() => { host.scrollTop = 0; });
          }}
        />
      );
    };
    render(
      <div data-testid="scroll-host" style={{ overflowY: "auto" }}>
        <Field />
      </div>,
    );
    const host = screen.getByTestId("scroll-host");
    Object.defineProperties(host, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 800 },
    });
    host.scrollTop = 320;

    fireEvent.click(screen.getByRole("button", { name: "Patrón" }));

    await waitFor(() => expect(host.scrollTop).toBe(320));
  });

  it("lets long notices wrap within their own padded surface", () => {
    render(<InlineNotice tone="warning">A long warning</InlineNotice>);

    const notice = screen.getByText("A long warning");
    expect(notice.style.boxSizing).toBe("border-box");
    expect(notice.style.overflowWrap).toBe("anywhere");
    expect(notice.getAttribute("role")).toBe("status");
    expect(notice.getAttribute("aria-live")).toBe("polite");
  });
});
