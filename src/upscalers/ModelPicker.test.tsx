// @vitest-environment happy-dom
import { forwardRef } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const focus = vi.hoisted(() => vi.fn());
vi.mock("../themes/runtime/navigationAccess", () => ({ createThemeNavigationAccess: () => ({ focus }) }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("@decky/ui", () => ({ Focusable: forwardRef<HTMLDivElement, any>(({ onActivate, onCancel, children, ...props }, ref) => <div {...props} ref={ref} onKeyDown={event => { if (event.key === "Escape") onCancel?.(event); }}>{children}</div>) }));
import { ModelPicker } from "./ModelPicker";
import type { BuildInfo, UpscalerChoice } from "./types";
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const base: BuildInfo = { id: "fsr", family: "fsr", version: "4.1.2", image: 1, cost: 1, available: true, supported: true, download_bytes: 1, models: ["lite", "full"] };
const choice: UpscalerChoice = { build: "fsr", quality: "balanced", sharpness: "soft", fg: "off" };

it("distinguishes the catalog's RDNA2 build from the same version without that variant", () => {
  render(<ModelPicker builds={[{ ...base, id: "fsr-4.1.1-rdna2", version: "4.1.1", models: [] }, { ...base, id: "fsr-4.1.1", version: "4.1.1", models: [] }]} choice={choice} inputs={{}} protonEnv={null} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  expect(screen.getByRole("button", { name: "FSR 4.1.1 (RDNA2) up.models.default" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "FSR 4.1.1 up.models.default" })).toBeTruthy();
});

it("opens comparison, chooses a catalog model and preserves the other draft settings", async () => {
  const onChange = vi.fn();
  render(<ModelPicker builds={[base]} choice={choice} inputs={{}} protonEnv={null} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  expect(screen.getByRole("table")).toBeTruthy();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(screen.getByRole("button", { pressed: true })));
  focus.mockClear();
  fireEvent.click(screen.getByRole("button", { name: /FSR 4.1.2 full/ }));
  expect(onChange).toHaveBeenCalledExactlyOnceWith({ ...choice, model: "full" });
  expect(screen.queryByRole("table")).toBeNull();
  expect(focus).not.toHaveBeenCalled();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(screen.getByRole("button", { name: "up.models.title" })));
});

it("shows the verified input requirement and refuses a blocked choice", () => {
  const onChange = vi.fn();
  render(<ModelPicker builds={[{ ...base, id: "native", models: [], engine: "proton" }]} choice={choice} inputs={{}} protonEnv={null} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  expect(screen.getByText("up.helix.needsFsr31")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /FSR 4.1.2 up.models.default/ }));
  expect(onChange).not.toHaveBeenCalled();
});

it("cancels without changing the draft and restores trigger focus", async () => {
  const onChange = vi.fn();
  render(<ModelPicker builds={[base]} choice={choice} inputs={{}} protonEnv={null} onChange={onChange} />);
  const trigger = screen.getByRole("button", { name: "up.models.title" });
  fireEvent.click(trigger);
  fireEvent.keyDown(screen.getByRole("button", { name: /FSR 4.1.2 full/ }), { key: "Escape" });
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByRole("table")).toBeNull();
  expect(focus).not.toHaveBeenCalled();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(trigger));
});
