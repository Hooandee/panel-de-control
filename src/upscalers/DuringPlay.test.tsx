// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ Navigation: { CloseSideMenus: vi.fn() } }));
vi.mock("../api", () => ({ getUpscalerLive: vi.fn(), pressUpscalerKey: vi.fn() }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./pageMemory", () => ({ holdPage: vi.fn() }));
vi.mock("./parts", () => ({
  Label: ({ children }: any) => <div>{children}</div>,
  ListCard: ({ children }: any) => <div>{children}</div>,
  Note: ({ children }: any) => <div>{children}</div>,
  ListRow: ({ label, on, busy, disabled, onPress }: any) => <button role={on === undefined ? "button" : "switch"} aria-checked={on} disabled={busy || disabled} onClick={onPress}>{label}</button>,
}));
import { pressUpscalerKey } from "../api";
import { DuringPlay } from "./LivePanel";
const props = { appid: "548430", optiscaler: true, fg: false, live: { fps: 60, render: 471, output: 800, generating: null, canPause: true }, onGenerating: vi.fn(), onCompare: vi.fn() };
afterEach(cleanup);

it("keeps an acknowledged FPS toggle when closing the QAM unmounts the caller", async () => {
  let finish!: () => void;
  vi.mocked(pressUpscalerKey).mockImplementation(() => new Promise((resolve) => { finish = () => resolve({ pressed: "fps" }); }));
  const first = render(<DuringPlay {...props} />);
  fireEvent.click(screen.getByRole("switch"));
  first.unmount();
  const second = render(<DuringPlay {...props} />);
  expect((screen.getByRole("switch") as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "up.play.menu" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => finish());
  expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true");
  second.unmount();
  render(<DuringPlay {...props} />);
  expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true");
  vi.mocked(pressUpscalerKey).mockResolvedValue({ pressed: "fps" });
  await act(async () => fireEvent.click(screen.getByRole("switch")));
  expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("false");
});
