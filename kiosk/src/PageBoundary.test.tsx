// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../src/system/uiDiagnostics", () => ({
  describeError: () => ({ code: "x", detail: "y" }),
  recordUiDiagnostic: vi.fn(),
}));

import { PageBoundary } from "./PageBoundary";

afterEach(cleanup);

describe("PageBoundary", () => {
  it("contains a crashing page and lets it retry", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    let crash = true;
    const Page = () => {
      if (crash) throw new Error("boom");
      return <p>ok</p>;
    };
    render(
      <PageBoundary where="kiosk:view" fallback={(retry) => <button onClick={retry}>retry</button>}>
        <Page />
      </PageBoundary>,
    );
    crash = false;
    fireEvent.click(screen.getByText("retry"));
    expect(screen.getByText("ok")).toBeTruthy();
  });
});
