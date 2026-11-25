// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  compose: vi.fn(),
}));

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, onClick, style, "aria-label": label }: any) => <button style={style} aria-label={label} onClick={onClick}>{children}</button>,
  Focusable: ({ children, onClick, style, "aria-label": label }: any) => <div style={style} aria-label={label} onClick={onClick}>{children}</div>,
  TextField: ({ value, onChange }: any) => <input value={value} onChange={onChange} />,
  GamepadButton: { DIR_LEFT: 11, DIR_RIGHT: 12, DIR_UP: 9, DIR_DOWN: 10, BUMPER_LEFT: 5, BUMPER_RIGHT: 6 },
  NavEntryPositionPreferences: { MAINTAIN_X: 2 },
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./PixelPreview", () => ({ PixelPreview: () => <div data-testid="stage" /> }));
vi.mock("../api", () => ({
  composeAccessoryLayout: api.compose,
  getAccessoryStickers: vi.fn(async () => ({ palette: { R: [255, 0, 0] }, stickers: { heart: [["RR", "RR"]], fire: [["R."], [".R"]] } })),
  listAccessoryDrawings: vi.fn(async () => ({ drawings: [] })),
}));

import { ComposerBody } from "./ComposerEditor";

afterEach(cleanup);

describe("layout editor", () => {
  it("renders, lists stickers and drops a new one where the backend places it", async () => {
    api.compose.mockImplementation(async (layout: { blocks: any[] }, place: number | null) => ({
      palette: [[0, 0, 0]], frames: [btoa(String.fromCharCode(...new Array(64 * 54).fill(0)))], delays: [100], firmwareAnimation: null,
      blocks: layout.blocks.map((b, i) => (i === place ? { ...b, x: 40, y: 20 } : b)),
      boxes: layout.blocks.map((b) => ({ x: b.x, y: b.y, w: 8, h: 8 })), mode: "static",
    }));
    vi.useFakeTimers();
    render(<ComposerBody initial={[]} onShow={() => undefined} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    expect(screen.getByText("accessories.compose.tab.pieces")).toBeTruthy();
    expect(screen.getByText("accessories.compose.mode.static")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("accessories.sticker.fire"));
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    const placed = api.compose.mock.calls.find(([, place]) => place !== null);
    expect(placed?.[0].blocks.at(-1).sticker).toBe("fire");
    expect(screen.getByText("accessories.compose.rotate")).toBeTruthy();
    vi.useRealTimers();
  });
});
