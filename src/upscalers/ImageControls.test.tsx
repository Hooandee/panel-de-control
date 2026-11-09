// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ImageControls } from "./ImageControls";
import type { UpscalerImageSettings } from "../api";
const api = vi.hoisted(() => ({ get: vi.fn(), set: vi.fn(), restore: vi.fn() }));
vi.mock("../api", () => ({ getUpscalerImageSettings: api.get, setUpscalerImageSettings: api.set, restoreUpscalerImageSettings: api.restore }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../system/uiEvents", () => ({ recordUiEvent: vi.fn() }));
vi.mock("../components/ContainedSlider", () => ({ ContainedSlider: ({ label, value, disabled, onChange }: any) => <label>{label}<input type="range" aria-label="sharpness" value={value} disabled={disabled} onChange={e => onChange(Number(e.target.value))} /></label> }));
vi.mock("./parts", () => ({
  Note: ({ children }: any) => <div>{children}</div>, Label: ({ children }: any) => <div>{children}</div>,
  ListCard: ({ children }: any) => <section>{children}</section>, Row: ({ children }: any) => <div>{children}</div>,
  ActionButton: ({ label, disabled, onPress }: any) => <button disabled={disabled} onClick={onPress}>{label}</button>,
  ListRow: ({ label, detail, disabled, onPress }: any) => <button disabled={disabled} onClick={onPress}>{label}{detail}</button>,
  SegmentRow: ({ value, options, disabled, onChange }: any) => <select aria-label="INT8" value={value} disabled={disabled} onChange={e => onChange(e.target.value)}>{options.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>,
}));
const original: UpscalerImageSettings = { supported: true, sharpness: { enabled: true, value: .3 }, int8: "auto", managed: false };
const props = { appid: "123", disabled: false, gameRunning: false, revision: "a" };
beforeEach(() => { api.get.mockResolvedValue(original); api.set.mockResolvedValue({ ...original, managed: true }); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });
it("hides unsupported configurations instead of presenting dead controls", async () => {
  api.get.mockResolvedValue({ supported: false, sharpness: null, int8: null, managed: false });
  const view = render(<ImageControls {...props} />);
  await act(async () => {});
  expect(view.container.textContent).toBe("");
});
it("applies only edited fields and coalesces the slider into an explicit save", async () => {
  render(<ImageControls {...props} />);
  const slider = await screen.findByRole("slider");
  fireEvent.change(slider, { target: { value: "60" } });
  fireEvent.change(slider, { target: { value: "70" } });
  expect(api.set).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("up.save"));
  await waitFor(() => expect(api.set).toHaveBeenCalledExactlyOnceWith("123", { sharpness: { enabled: true, value: .7 } }));
});
it("preserves automatic sharpness when editing INT8 only", async () => {
  api.get.mockResolvedValue({ ...original, sharpness: { enabled: null, value: null } });
  render(<ImageControls {...props} />);
  fireEvent.change(await screen.findByRole("combobox"), { target: { value: "off" } });
  fireEvent.click(screen.getByText("up.save"));
  await waitFor(() => expect(api.set).toHaveBeenCalledExactlyOnceWith("123", { int8: "off" }));
});
it("does not write discarded adjustments", async () => {
  render(<ImageControls {...props} />);
  fireEvent.change(await screen.findByRole("slider"), { target: { value: "90" } });
  fireEvent.click(screen.getByText("up.discard"));
  expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("30");
  expect(api.set).not.toHaveBeenCalled();
});
it("keeps edits after failure and retries the same values", async () => {
  api.set.mockRejectedValueOnce(new Error("write_failed"));
  render(<ImageControls {...props} />);
  fireEvent.change(await screen.findByRole("slider"), { target: { value: "80" } });
  fireEvent.click(screen.getByText("up.save"));
  await screen.findByText("up.error.generic");
  fireEvent.click(screen.getByText("up.save"));
  await waitFor(() => expect(api.set).toHaveBeenCalledTimes(2));
  expect(api.set.mock.calls[0]).toEqual(api.set.mock.calls[1]);
});
it("blocks writes while a game is running", async () => {
  render(<ImageControls {...props} disabled gameRunning />);
  const slider = await screen.findByRole("slider");
  expect((slider as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true);
  fireEvent.change(slider, { target: { value: "60" } });
  expect(api.set).not.toHaveBeenCalled();
});
it("restores only through the backend and displays its readback", async () => {
  api.get.mockResolvedValue({ ...original, managed: true });
  api.restore.mockResolvedValue({ ...original, sharpness: { enabled: false, value: .2 } });
  render(<ImageControls {...props} />);
  fireEvent.click(await screen.findByText("up.image.restore"));
  await waitFor(() => expect(api.restore).toHaveBeenCalledExactlyOnceWith("123"));
  await waitFor(() => expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("0"));
});
it("ignores an old game response after switching games", async () => {
  let resolve!: (value: UpscalerImageSettings) => void;
  api.get.mockReturnValueOnce(new Promise(r => { resolve = r; }));
  api.get.mockResolvedValueOnce({ ...original, int8: null });
  const view = render(<ImageControls {...props} />);
  view.rerender(<ImageControls {...props} appid="456" />);
  await screen.findByRole("slider");
  await act(async () => { resolve(original); });
  expect(screen.queryByRole("combobox")).toBeNull();
});

it("refreshes readback when quality changes during an image save", async () => {
  let finish!: (value: UpscalerImageSettings) => void;
  api.set.mockReturnValueOnce(new Promise(r => { finish = r; }));
  const view = render(<ImageControls {...props} />);
  fireEvent.change(await screen.findByRole("slider"), { target: { value: "70" } });
  fireEvent.click(screen.getByText("up.save"));
  view.rerender(<ImageControls {...props} revision="b" />);
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  const saved = { ...original, sharpness: { enabled: true, value: .7 }, managed: true };
  api.get.mockResolvedValue(saved);
  await act(async () => { finish(saved); });
  await waitFor(() => expect((screen.getByRole("slider") as HTMLInputElement).value).toBe("70"));
  expect(api.get).toHaveBeenCalledTimes(3);
});

it.each(["slider", "int8"])("clears the previous saved message when editing %s", async (control) => {
  render(<ImageControls {...props} />);
  fireEvent.change(await screen.findByRole("slider"), { target: { value: "60" } });
  fireEvent.click(screen.getByText("up.save"));
  await screen.findByText("up.image.saved");
  if (control === "slider") fireEvent.change(screen.getByRole("slider"), { target: { value: "80" } });
  if (control === "int8") fireEvent.change(screen.getByRole("combobox"), { target: { value: "off" } });
  expect(screen.queryByText("up.image.saved")).toBeNull();
  expect(screen.getByText("up.save")).toBeTruthy();
});

it("shows the slider for automatic sharpness without writing until edited", async () => {
  api.get.mockResolvedValue({ ...original, sharpness: { enabled: null, value: null } });
  render(<ImageControls {...props} />);
  const slider = await screen.findByRole("slider");
  expect(api.set).not.toHaveBeenCalled();
  fireEvent.change(slider, { target: { value: "40" } });
  fireEvent.click(screen.getByText("up.save"));
  await waitFor(() => expect(api.set).toHaveBeenCalledWith("123", { sharpness: { enabled: true, value: .4 } }));
});
it("zero disables sharpening while keeping its slider visible", async () => {
  render(<ImageControls {...props} />);
  fireEvent.change(await screen.findByRole("slider"), { target: { value: "0" } });
  fireEvent.click(screen.getByText("up.save"));
  await waitFor(() => expect(api.set).toHaveBeenCalledWith("123", { sharpness: { enabled: false, value: 0 } }));
  expect(screen.getByRole("slider")).toBeTruthy();
});
