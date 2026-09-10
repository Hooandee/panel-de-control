// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  modal: null as ReactNode | null,
  submitReport: vi.fn(async () => ({ ok: true, code: "PDC-TEST" })),
}));

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, ...props }: { children?: ReactNode }) => (
    <button type="button" {...props}>{children}</button>
  ),
  Focusable: ({
    children,
    onActivate,
    onClick,
    noFocusRing: _noFocusRing,
    ...props
  }: {
    children?: ReactNode;
    onActivate?: () => void;
    onClick?: () => void;
    noFocusRing?: boolean;
    [key: string]: unknown;
  }) => createElement(
    onActivate || onClick ? "button" : "div",
    {
      ...props,
      ...(onActivate || onClick ? { type: "button" } : {}),
      onClick: onClick ?? onActivate,
    },
    children,
  ),
  ModalRoot: ({ children }: { children?: ReactNode }) => <>{children}</>,
  showModal: (node: ReactNode) => { mocks.modal = node; },
  TextField: ({ value, onChange }: { value: string; onChange: (event: unknown) => void }) => (
    <input value={value} onChange={onChange} />
  ),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("../api", () => ({
  getDevice: vi.fn(() => new Promise(() => {})),
  submitReport: mocks.submitReport,
}));

vi.mock("../launch/reportContext", () => ({ launchReportContext: vi.fn(async () => ({})) }));
vi.mock("../deckyInternal", () => ({ quickAccessTabDiagnostics: vi.fn(() => ({})) }));
vi.mock("../qamDocument", () => ({ getQamDocument: vi.fn(() => document) }));
vi.mock("./FocusRoot", () => ({ FocusRoot: ({ children }: { children: ReactNode }) => <>{children}</> }));

import { openReportModal } from "./ReportModal";

describe("ReportModal request type", () => {
  afterEach(() => {
    cleanup();
    mocks.modal = null;
    mocks.submitReport.mockClear();
  });

  it("starts as a problem and submits a feature request without losing its area or text", async () => {
    openReportModal();
    render(mocks.modal);

    const problem = screen.getByRole("radio", { name: "report.kind.bug" });
    const feature = screen.getByRole("radio", { name: "report.kind.feature" });
    expect(problem.getAttribute("aria-checked")).toBe("true");
    expect(feature.getAttribute("aria-checked")).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: "report.cat.themes" }));
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Add automatic theme rotation" },
    });
    fireEvent.click(feature);

    expect(feature.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("report.intro.feature")).toBeTruthy();
    expect(screen.getByRole("textbox")).toHaveProperty(
      "value",
      "Add automatic theme rotation",
    );

    fireEvent.click(screen.getByRole("button", { name: "report.send" }));

    await waitFor(() => expect(mocks.submitReport).toHaveBeenCalledWith(
      ["themes"],
      "Add automatic theme rotation",
      expect.objectContaining({ report_kind: "feature" }),
    ));
    expect(await screen.findByText("report.done.thanks.feature")).toBeTruthy();
    expect(screen.getByText("report.code.hint.feature")).toBeTruthy();
  });
});
