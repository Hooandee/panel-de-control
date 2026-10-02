// @vitest-environment happy-dom
import { render } from "@testing-library/react";
import { Component, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const recorded: unknown[][] = [];
vi.mock("../api", () => ({
  recordUiDiagnostic: (...args: unknown[]) => {
    recorded.push(args);
    return Promise.resolve(true);
  },
}));

import { ReportingBoundary } from "./ReportingBoundary";

class Outer extends Component<{ children?: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <p>decky error view</p> : this.props.children;
  }
}

function Broken(): never {
  throw new RangeError("bad watts");
}

describe("ReportingBoundary", () => {
  it("records a render error and lets the outer boundary show it", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const view = render(
      <Outer>
        <ReportingBoundary where="section:power">
          <Broken />
        </ReportingBoundary>
      </Outer>,
    );
    expect(view.getByText("decky error view")).toBeTruthy();
    expect(recorded[0][0]).toBe("frontend");
    expect(recorded[0][1]).toBe("range_error");
    expect(String(recorded[0][2])).toContain("section:power: bad watts");
  });
});
