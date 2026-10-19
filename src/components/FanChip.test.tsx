// @vitest-environment happy-dom
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FanChip } from "./FanChip";

describe("FanChip", () => {
  it("shows the commanded duty when the fan has no tachometer", () => {
    const { container } = render(<FanChip label="Fan" rpm={null} values={[]} dutyPercent={42} />);
    expect(container.textContent).toContain("42%");
    expect(container.textContent).not.toContain("RPM");
  });

  it("keeps RPM for fans with a tachometer", () => {
    const { container } = render(<FanChip label="Fan" rpm={3100} values={[]} />);
    expect(container.textContent).toContain("3100RPM");
  });
});
