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

it("shows a direct list of usable choices without unsupported rows or technical columns", () => {
  render(<ModelPicker builds={[base, { ...base, id: "unavailable", available: false }, { ...base, id: "unsupported", supported: false }]} choice={choice} inputs={{}} protonEnv={null} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  expect(screen.getAllByRole("radio")).toHaveLength(2);
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.getByText("up.bar.image")).toBeTruthy();
  expect(screen.getByText("up.bar.perf")).toBeTruthy();
});

it("opens comparison, chooses a catalog model and preserves the other draft settings", async () => {
  const onChange = vi.fn();
  render(<ModelPicker builds={[base]} choice={choice} inputs={{}} protonEnv={null} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  expect(screen.getByRole("radiogroup")).toBeTruthy();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(screen.getByRole("radio", { checked: true })));
  focus.mockClear();
  fireEvent.click(screen.getByRole("radio", { name: /FSR 4.1.2 up.model.full/ }));
  expect(onChange).toHaveBeenCalledExactlyOnceWith({ ...choice, model: "full" });
  expect(screen.queryByRole("radiogroup")).toBeNull();
  expect(focus).not.toHaveBeenCalled();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(screen.getByRole("button", { name: "up.section.model" })));
});

it("omits a build whose game input requirement is absent", () => {
  render(<ModelPicker builds={[{ ...base, id: "native", models: [], engine: "proton" }]} choice={choice} inputs={{}} protonEnv={null} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  expect(screen.queryAllByRole("radio")).toHaveLength(0);
});

it("cancels without changing the draft and restores trigger focus", async () => {
  const onChange = vi.fn();
  render(<ModelPicker builds={[base]} choice={choice} inputs={{}} protonEnv={null} onChange={onChange} />);
  const trigger = screen.getByRole("button", { name: "up.section.model" });
  fireEvent.click(trigger);
  fireEvent.keyDown(screen.getByRole("radio", { name: /FSR 4.1.2 up.model.full/ }), { key: "Escape" });
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByRole("radiogroup")).toBeNull();
  expect(focus).not.toHaveBeenCalled();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(trigger));
});

it("focuses the first available option when the current build is filtered out", async () => {
  render(<ModelPicker builds={[{ ...base, supported: false }, { ...base, id: "other", version: "4.1.1", models: [] }]} choice={choice} inputs={{}} protonEnv={null} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  await waitFor(() => expect(focus).toHaveBeenCalledWith(screen.getByRole("radio", { name: "FSR 4.1.1" })));
});

it("separates DLL models and keeps the OptiScaler choices in their own dropdown group", () => {
  const dll: BuildInfo = { ...base, id: "direct", engine: "dll", way: "fsr", models: [], dll_names: ["amd_fidelityfx_upscaler_dx12.dll"] };
  const onChange = vi.fn();
  render(<ModelPicker builds={[base, dll]} choice={choice} inputs={{ fsr31: ["amd_fidelityfx_upscaler_dx12.dll"] }} dllTargets={["bin/amd_fidelityfx_upscaler_dx12.dll"]} protonEnv={null} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  expect(screen.getAllByRole("radio")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  fireEvent.click(screen.getByText("DLL"));
  expect(screen.getAllByRole("radio")).toHaveLength(1);
  fireEvent.click(screen.getByRole("radio"));
  expect(onChange).toHaveBeenCalledWith({ ...choice, build: "direct", model: null });
});

it("does not offer a DLL replacement for an embedded FSR integration", () => {
  const dll: BuildInfo = { ...base, id: "direct", engine: "dll", way: "fsr", models: [] };
  render(<ModelPicker builds={[base, dll]} choice={choice} inputs={{ fsr31: ["game.exe"] }} dllTargets={[]} protonEnv={null} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  fireEvent.click(screen.getByText("DLL"));
  expect(screen.queryAllByRole("radio")).toHaveLength(0);
  expect(screen.getByText("up.mode.noDll")).toBeTruthy();
});

const provider = "amd_fidelityfx_upscaler_dx12.dll";
const loader = "amd_fidelityfx_loader_dx12.dll";
const framegen = "amd_fidelityfx_framegeneration_dx12.dll";

it.each([
  { targets: ["_storage_/amd_fidelityfx_dx12.dll", `_storage_/${loader}`, `_storage_/${provider}`, loader, provider], expected: ["FSR 4.1.2"] },
  { targets: [`bin/${loader}`, `bin/${provider}`], expected: ["FSR 4.0.2c", "FSR 4.1.1", "FSR 4.1.2"] },
  { targets: [`other/${loader}`, `bin/${provider}`], expected: ["FSR 4.1.1", "FSR 4.1.2"] },
  { targets: [loader], expected: ["FSR 4.1.1", "FSR 4.1.2"] },
  { targets: [], expected: [] },
])("offers only DLL packages compatible with every target: $targets", ({ targets, expected }) => {
  const packages: BuildInfo[] = [
    { ...base, id: "provider", version: "4.0.2c", dll_names: [provider] },
    { ...base, id: "loader-provider", version: "4.1.1", dll_names: [loader, provider] },
    { ...base, id: "complete", version: "4.1.2", dll_names: [loader, provider, framegen] },
  ].map(build => ({ ...build, engine: "dll", way: "fsr", models: [] }));
  render(<ModelPicker builds={packages} choice={{ ...choice, build: "complete" }} inputs={{}} dllTargets={targets} protonEnv={null} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  expect(screen.queryAllByRole("radio").map(row => row.getAttribute("aria-label"))).toEqual(expected);
});

it.each([
  { targets: ["_storage_/AMD_FIDELITYFX_DX12.DLL", `_storage_/${loader}`, `_storage_/${provider}`, loader, provider], offered: true },
  { targets: ["bin/amd_fidelityfx_dx12.dll", `bin/${loader}`], offered: true },
  { targets: ["bin/amd_fidelityfx_dx12.dll", `other/${loader}`], offered: false },
])("uses legacy bridge resources only for legacy folders: $targets", ({ targets, offered }) => {
  const dll: BuildInfo = { ...base, id: "direct", engine: "dll", way: "fsr", models: [], dll_names: [provider], dll_legacy_names: [loader, framegen] };
  render(<ModelPicker builds={[dll]} choice={{ ...choice, build: "direct" }} inputs={{}} dllTargets={targets} protonEnv={null} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  expect(screen.queryAllByRole("radio")).toHaveLength(offered ? 1 : 0);
});

it("selects Mako without replacing the saved OptiScaler choice", () => {
  const onSpatial = vi.fn(); const onChange = vi.fn();
  render(<ModelPicker builds={[base]} choice={choice} inputs={{}} protonEnv={null} onChange={onChange} onSpatial={onSpatial} />);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  fireEvent.click(screen.getByText("Mako"));
  expect(onSpatial).toHaveBeenCalledWith(true);
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByRole("radiogroup")).toBeNull();
});

it("keeps DLL open when leaving Mako before choosing a model", () => {
  const dll = { ...base, id: "dll", version: "4.0.2c", engine: "dll" as const, models: undefined, dll_names: ["amd_fidelityfx_upscaler_dx12.dll"] };
  const props = { builds: [base, dll], choice, inputs: {}, protonEnv: null, onChange: vi.fn(), onSpatial: vi.fn(), dllTargets: ["/game/amd_fidelityfx_upscaler_dx12.dll"] };
  const page = render(<ModelPicker {...props} spatial />);
  expect(screen.queryByRole("button", { name: "up.section.model" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  fireEvent.click(screen.getByText("DLL"));
  page.rerender(<ModelPicker {...props} spatial={false} />);
  expect(screen.getByRole("radio", { name: "FSR 4.0.2c" })).toBeTruthy();
  expect(screen.queryByRole("radio", { name: /4.1.2/ })).toBeNull();
  expect(props.onSpatial).toHaveBeenCalledWith(false);
});

it.each([
  ["optiscaler", "pdc-up-optiscaler-icon", false],
  ["dll", "pdc-up-dll-icon", false],
  ["mako", "pdc-up-mako-icon", true],
] as const)("keeps the selected %s icon visible under theme rules", (engine, iconClass, spatial) => {
  render(<ModelPicker builds={[{ ...base, engine: engine === "dll" ? "dll" : "optiscaler" }]} choice={choice}
    inputs={{}} protonEnv={null} onChange={vi.fn()} onSpatial={vi.fn()} spatial={spatial} />);
  const icon = screen.getByRole("button", { name: "up.models.title" }).querySelector<SVGElement>(`.${iconClass}`);
  expect(icon).not.toBeNull();
  expect(icon?.style.getPropertyValue("display")).toBe("inline-block");
  expect(icon?.style.getPropertyPriority("display")).toBe("important");
});

it("reports an unchosen DLL engine and hides empty table headers", () => {
  const onPendingChoice = vi.fn();
  render(<ModelPicker builds={[base]} choice={choice} inputs={{}} protonEnv={null} onChange={vi.fn()} onPendingChoice={onPendingChoice} />);
  fireEvent.click(screen.getByRole("button", { name: "up.models.title" }));
  fireEvent.click(screen.getByText("DLL"));
  expect(onPendingChoice).toHaveBeenLastCalledWith(true);
  expect(screen.getByText("up.mode.noDll")).toBeTruthy();
  expect(screen.queryByText("up.bar.image")).toBeNull();
  expect(screen.queryByText("up.bar.perf")).toBeNull();
});

it("tags a build that may fall back to another version without blocking it", () => {
  const onChange = vi.fn();
  const fallback = { ...base, id: "dll-fp8", engine: "optiscaler" as const, models: [], may_fallback: "3.1.6" };
  render(<ModelPicker builds={[fallback, { ...base, id: "plain", version: "4.0.2", models: [] }]} choice={{ ...choice, build: "dll-fp8" }} inputs={{}} protonEnv={null} onChange={onChange} />);
  expect(screen.getAllByText("up.build.mayUse")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "up.section.model" }));
  expect(screen.getAllByText("up.build.mayUse")).toHaveLength(2);
  fireEvent.click(screen.getByRole("radio", { name: "FSR 4.1.2" }));
  expect(onChange).toHaveBeenCalledWith({ ...choice, build: "dll-fp8", model: null });
});
