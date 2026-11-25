// @vitest-environment happy-dom
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const language = vi.hoisted(() => ({ current: "es", listeners: new Set<() => void>() }));
vi.mock("@decky/ui", () => ({ staticClasses: { Title: "title" } }));
vi.mock("../i18n", () => ({
  getCurrentLanguage: () => language.current,
  subscribeLanguage: (listener: () => void) => {
    language.listeners.add(listener);
    return () => language.listeners.delete(listener);
  },
  translate: () => language.current === "es" ? "Ajustes" : "Settings",
}));
import { QamTabTitle } from "./QamTabTitle";
afterEach(() => { cleanup(); language.current = "es"; });
it("translates in place and preserves custom titles through language changes", () => {
  const translated = render(<QamTabTitle labelKey="nav.settings" />);
  const custom = render(<QamTabTitle label="Mi vista" labelKey="nav.settings" />);
  const node = translated.container.firstChild;
  expect(node?.textContent).toBe("Ajustes");
  act(() => { language.current = "en"; language.listeners.forEach(listener => listener()); });
  expect(translated.container.firstChild).toBe(node);
  expect(node?.textContent).toBe("Settings");
  expect(custom.container.textContent).toBe("Mi vista");
  act(() => { language.current = "es"; language.listeners.forEach(listener => listener()); });
  expect(node?.textContent).toBe("Ajustes");
  cleanup();
  expect(language.listeners.size).toBe(0);
});
