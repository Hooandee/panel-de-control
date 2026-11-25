// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FanCurveGraph } from "./FanCurveGraph";

describe("FanCurveGraph axis", () => {
  afterEach(cleanup);

  it("writes the percent sign on each Y label instead of a stray one over the 100", () => {
    const { container } = render(
      <FanCurveGraph points={[[40, 0], [95, 255]]} liveTemp={null} editable={false} onChange={() => {}} />,
    );
    const texts = Array.from(container.querySelectorAll("text")).map((node) => node.textContent);
    expect(texts).toEqual(expect.arrayContaining(["0%", "50%", "100%", "°C"]));
    expect(texts).not.toContain("%");
  });
});
