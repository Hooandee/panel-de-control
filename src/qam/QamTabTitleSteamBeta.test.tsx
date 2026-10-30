// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
vi.mock("@decky/ui", () => ({ staticClasses: undefined }));
vi.mock("../i18n", () => ({
  getCurrentLanguage: () => "es",
  subscribeLanguage: () => () => {},
  translate: () => "Ajustes",
}));
import { QamTabTitle } from "./QamTabTitle";
afterEach(cleanup);
it("still renders its title when Steam no longer exposes Decky's static classes", () => {
  expect(render(<QamTabTitle labelKey="nav.settings" />).container.textContent).toBe("Ajustes");
});
