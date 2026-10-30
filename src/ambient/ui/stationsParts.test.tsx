// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ Focusable: () => null, DialogButton: () => null }));

import { sheetRoom } from "./stationsParts";

function box(top: number, extra: Partial<HTMLElement> = {}): HTMLElement {
  return { getBoundingClientRect: () => ({ top }) as DOMRect, scrollTop: 0, clientHeight: 0, ...extra } as HTMLElement;
}

function view(paddingTop: string, paddingBottom: string): Window {
  return { getComputedStyle: () => ({ paddingTop, paddingBottom }) } as unknown as Window;
}

describe("sheetRoom", () => {
  it("leaves out the extra padding Steam gives dialogs on larger screens", () => {
    expect(sheetRoom(box(92), box(88, { clientHeight: 463 }), view("4px", "4px"))).toBe(455);
  });

  it("matches the dialog height when Steam adds no padding", () => {
    expect(sheetRoom(box(80), box(80, { clientHeight: 372 }), view("0px", "0px"))).toBe(372);
  });

  it("subtracts the header above the sheet inside the scroller", () => {
    expect(sheetRoom(box(130), box(100, { clientHeight: 400 }), view("0px", "0px"))).toBe(370);
  });
});
