import { describe, expect, it } from "vitest";
import { describePreset, presetDetail, presetLabel, swatchBackground } from "./consoleLight";

const t = (key: string, vars?: Record<string, string | number>) =>
  vars ? `${key}(${Object.values(vars).join("|")})` : key;

describe("PS5 light presets", () => {
  it("reads colours and styles from the kernel names", () => {
    expect(describePreset("pink_violet_dim")).toEqual({ off: false, colors: ["pink", "violet"], styles: ["dim"] });
    expect(describePreset("blue_to_richblue")).toEqual({ off: false, colors: ["blue"], styles: ["fade"] });
    expect(describePreset("zoneb_orange_pulse")).toEqual({ off: false, colors: ["orange"], styles: ["pulse"] });
  });

  it("names off, single and mixed colours", () => {
    expect(presetLabel("off", t)).toBe("console.light.off");
    expect(presetLabel("blue_rich", t)).toBe("Console.light.color.blue");
    expect(presetLabel("purplish_blue_white", t)).toBe("Console.light.and(console.light.color.purple, console.light.color.blue|console.light.color.white)");
    expect(presetLabel("sunrise", t)).toBe("console.light.style.sunrise");
  });

  it("shows a colour it does not know by its kernel name instead of guessing", () => {
    expect(describePreset("red_rich").colors).toEqual([]);
    expect(presetLabel("red_rich", t)).toBe("Red rich");
    expect(swatchBackground("red_rich")).toContain("#5b6472");
  });

  it("lists the styles as details", () => {
    expect(presetDetail("pink_breathe_fast", t)).toBe("console.light.style.breathe · console.light.style.fast");
    expect(presetDetail("purple", t)).toBe("");
  });

  it("previews one colour flat and several as a gradient", () => {
    expect(swatchBackground("off")).toBe("transparent");
    expect(swatchBackground("orange_dim")).toBe("#ff8a2b");
    expect(swatchBackground("blue_white_anim")).toContain("linear-gradient");
  });
});
