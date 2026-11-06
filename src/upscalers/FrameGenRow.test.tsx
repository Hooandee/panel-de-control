// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ getLsfgStatus: vi.fn(), adoptForeignLsfg: vi.fn(), installLsfg: vi.fn(), setLsfgGame: vi.fn(), restoreForeignLsfg: vi.fn(), writeLaunchOptions: vi.fn() }));
vi.mock("../api", () => api);
vi.mock("./losslessBranch", () => ({ readLosslessBranch: async () => ({ selected: "lsfg-vk", available: true, supported: true }), switchLosslessBranch: vi.fn() }));
vi.mock("../launch/steamApi", () => ({ readAppDetails: async () => ({ launch: "" }), writeLaunchOptions: api.writeLaunchOptions }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../components/ExperimentalBadge", () => ({ ExperimentalBadge: ({ children }: any) => <span>{children}</span> }));
vi.mock("./parts", () => ({
  ActionButton: ({ label, onPress }: any) => <button onClick={onPress}>{label}</button>,
  PickerButton: ({ label, value, options, onChange }: any) => <select aria-label={label} value={value} onChange={e => onChange(e.target.value)}>{options.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>,
  Label: ({ children }: any) => <div>{children}</div>, ListCard: ({ children }: any) => <div>{children}</div>,
  ListRow: ({ label }: any) => <div>{label}</div>, Notice: ({ children }: any) => <div>{children}</div>, Row: ({ children }: any) => <div>{children}</div>,
}));
import { FrameGenRow } from "./FrameGenRow";
const foreign = { installed: false, foreign: true, lossless: true, dll: "/lossless/lsfg-vk.dll", profiles: {}, foreign_backup: false };
afterEach(() => { cleanup(); vi.resetAllMocks(); });
it("offers detected foreign Lossless without changing it until explicit adoption", async () => {
  api.getLsfgStatus.mockResolvedValue(foreign);
  const onOptiscaler = vi.fn();
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{}} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={onOptiscaler} />);
  const select = await screen.findByRole("combobox", { name: "up.fg.title" });
  expect(screen.queryByText("up.lsfg.foreign")).toBeNull();
  expect(screen.queryByRole("button", { name: "up.lsfg.adopt" })).toBeNull();
  fireEvent.change(select, { target: { value: "lsfg" } });
  await waitFor(() => expect((select as HTMLSelectElement).value).toBe("lsfg"));
  expect(api.adoptForeignLsfg).not.toHaveBeenCalled();
  expect(api.installLsfg).not.toHaveBeenCalled();
  expect(api.setLsfgGame).not.toHaveBeenCalled();
  expect(api.writeLaunchOptions).not.toHaveBeenCalled();
  api.adoptForeignLsfg.mockResolvedValue({ ...foreign, foreign: false, foreign_backup: true });
  api.installLsfg.mockResolvedValue({ ...foreign, installed: true, foreign: false });
  api.setLsfgGame.mockResolvedValue({ env: { LSFGVK_PROFILE: "pdc-1", ENABLE_GAMESCOPE_WSI: "0" } });
  api.writeLaunchOptions.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "up.lsfg.adopt" }));
  await waitFor(() => expect(onOptiscaler).toHaveBeenCalledWith("off", null));
  expect(api.adoptForeignLsfg).toHaveBeenCalledOnce();
  expect(api.installLsfg).toHaveBeenCalledOnce();
  expect(api.setLsfgGame).toHaveBeenCalledWith("1", { multiplier: 2, flow: "balanced", performance: true });
});
