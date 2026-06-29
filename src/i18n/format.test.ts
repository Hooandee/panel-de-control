import { describe, it, expect } from "vitest";
import { format } from "./format";

describe("format", () => {
  it("returns the template when there are no params", () => {
    expect(format("Hola mundo")).toBe("Hola mundo");
  });
  it("interpolates {named} params", () => {
    expect(format("Versión {v}", { v: "0.1.0" })).toBe("Versión 0.1.0");
  });
  it("interpolates numbers", () => {
    expect(format("{n} zonas", { n: 3 })).toBe("3 zonas");
  });
  it("leaves unknown placeholders intact", () => {
    expect(format("Hola {name}", {})).toBe("Hola {name}");
  });
});
