// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ captureUpscalerFrame: vi.fn() }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("@decky/ui", () => ({ ModalRoot: ({ children }: any) => <div>{children}</div>, SliderField: () => null }));
vi.mock("../navigation/showModal", () => ({ showModal: vi.fn() }));
vi.mock("./overlays", () => ({ setCompareGhost: vi.fn() }));
vi.mock("./pageMemory", () => ({ holdPage: vi.fn() }));
vi.mock("./parts", () => {
  const Box = ({ children }: any) => <div>{children}</div>;
  return { Label: Box, Note: Box, Row: Box, SegmentRow: () => null, Spinner: () => null,
    ActionButton: ({ label, onPress, disabled }: any) => <button onClick={onPress} disabled={disabled}>{label}</button> };
});

import { captureUpscalerFrame } from "../api";
import { showModal } from "../navigation/showModal";
import { CompareView } from "./CompareView";

afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("labels each observed engine independently of the installed build", async () => {
  const shot = { build: "fsr-4.1.2", image: "data:image/png;base64,a" };
  vi.mocked(captureUpscalerFrame)
    .mockResolvedValueOnce({ ...shot, id: "first", upscaler: "FSR 3.X" })
    .mockResolvedValueOnce({ ...shot, id: "second", upscaler: "XeSS" });
  render(<CompareView appid="compare-engines" gameRunning onClose={vi.fn()} />);
  await act(async () => { fireEvent.click(screen.getByText("up.compare.shootFirst")); });
  expect(screen.getByText("up.compare.first, FSR")).toBeTruthy();
  expect(screen.queryByText(/3\.X|4\.1\.2/)).toBeNull();
  await act(async () => { fireEvent.click(screen.getByText("up.compare.shootSecond")); });
  fireEvent.click(screen.getByText("up.compare.show"));
  render(vi.mocked(showModal).mock.calls[0][0]);
  expect(screen.getByText("up.compare.first, FSR")).toBeTruthy();
  expect(screen.getByText("up.compare.second, XeSS")).toBeTruthy();
});

it.each([undefined, "DLSS", "FSR 3.1.5", "FSR 4.1.2"])("preserves precise observations and legacy shots (%s)", async (upscaler) => {
  vi.mocked(captureUpscalerFrame).mockResolvedValue({ id: "legacy", build: "fsr-4.1.2", image: "data:image/png;base64,a", upscaler });
  render(<CompareView appid={`compare-${upscaler}`} gameRunning onClose={vi.fn()} />);
  await act(async () => { fireEvent.click(screen.getByText("up.compare.shootFirst")); });
  expect(screen.getByText(upscaler ? `up.compare.first, ${upscaler}` : "up.compare.first")).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByText("up.compare.shootSecond")); });
  fireEvent.click(screen.getByText("up.compare.show"));
  render(vi.mocked(showModal).mock.calls[0][0]);
  expect(screen.getByText(upscaler ? `up.compare.second, ${upscaler}` : "up.compare.second")).toBeTruthy();
});
