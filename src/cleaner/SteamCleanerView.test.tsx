// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CleanerController } from "./useSteamCleaner";
import type { CleanerEntry, CleanerState } from "./types";

vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Focusable: ({ children, onActivate: _activate, onCancel: _cancel, onOKActionDescription: _legend, "flow-children": _flow, ...props }: { children?: ReactNode; [key: string]: unknown }) => <div {...props}>{children}</div>,
  TextField: ({ label, value, onChange }: { label: string; value: string; onChange: (event: unknown) => void }) => <label>{label}<input value={value} onChange={onChange} /></label>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ lang: "en", t: (key: string, values?: Record<string, unknown>) => `${key}${values ? ` ${Object.values(values).join(" ")}` : ""}` }) }));
vi.mock("../system/pdcStorage", () => ({
  readFlag: (key: string) => localStorage.getItem(key) === "1",
  writeFlag: (key: string, value: boolean) => localStorage.setItem(key, value ? "1" : "0"),
  onPrefsHealed: () => () => {},
}));
vi.mock("./steamMetadata", () => ({
  readCleanerMetadata: () => new Map(),
  readInstalledCleanerMetadata: () => [{ appid: "42", name: "Installed Game", coverUrls: [] }],
}));
import { SteamCleanerView } from "./SteamCleanerView";

const entry = (id: string, overrides: Partial<CleanerEntry> = {}): CleanerEntry => ({ id, game_id: "game", appid: "10", name: "Game", kind: "shadercache", library_id: "library", library_label: "Internal drive", bytes: 1_000_000, installation: "installed", blocked_reason: null, warnings: [], ...overrides });
const state = (overrides: Partial<CleanerState> = {}): CleanerState => ({ schema_version: 1, available: true, status: "ready", scan_id: "scan", coverage_complete: true, entries: [entry("cache"), entry("prefix", { kind: "compatdata" })], libraries: [{ id: "library", label: "Internal drive", available: true, reason: null }], totals: { shadercache: 1_000_000, compatdata: 1_000_000, unknown: 0 }, progress: { processed: 0, total: null }, error: null, last_result: null, ...overrides });
const controller = (overrides: Partial<CleanerController> = {}): CleanerController => ({ state: state(), plan: null, result: null, error: null, loading: false, pending: null, busy: false, cancelling: false, scan: vi.fn(async () => {}), prepare: vi.fn(async () => {}), execute: vi.fn(async () => {}), cancel: vi.fn(async () => {}), refresh: vi.fn(async () => {}), dismissPlan: vi.fn(), dismissResult: vi.fn(), ...overrides });
afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("Steam Cleaner interface", () => {
  it("shows installed games immediately while their cleanup sizes are calculated", () => {
    render(<SteamCleanerView embedded controller={controller({ state: null, loading: true })} />);
    expect(screen.getByText("Installed Game")).toBeTruthy();
    expect(screen.getByText("cleaner.calculating")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /Installed Game/ })).toBeNull();
  });

  it("does not claim Steam is unavailable before the first scan", () => {
    render(<SteamCleanerView controller={controller({ state: state({ available: false, status: "idle", scan_id: null, entries: [], libraries: [] }) })} />);
    expect(screen.queryByText("cleaner.unavailable")).toBeNull();
    expect(screen.getByRole("button", { name: "cleaner.scan" })).toBeTruthy();
  });

  it("starts with an empty selection and bulk selection never adds game data", () => {
    const c = controller();
    render(<SteamCleanerView controller={c} />);
    expect(screen.queryByRole("button", { name: "cleaner.cleanSelection" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "cleaner.selectCaches" }));
    fireEvent.click(screen.getByRole("button", { name: "cleaner.cleanSelection" }));
    expect(c.prepare).toHaveBeenLastCalledWith(["cache"]);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.gameDetails Game" }));
    const prefix = screen.getByRole("checkbox", { name: "cleaner.kind.compatdata · Internal drive" });
    expect(prefix.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(prefix);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.cleanSelection" }));
    expect(c.prepare).toHaveBeenLastCalledWith(["cache", "prefix"]);
  });

  it("shows a mixed game indicator until every available option is selected", () => {
    render(<SteamCleanerView controller={controller()} />);
    const game = screen.getByRole("checkbox", { name: "cleaner.selectGameCaches Game" });
    fireEvent.click(screen.getByRole("button", { name: "cleaner.gameDetails Game" }));
    const cache = screen.getByRole("checkbox", { name: "cleaner.kind.shadercache · Internal drive" });
    const prefix = screen.getByRole("checkbox", { name: "cleaner.kind.compatdata · Internal drive" });

    fireEvent.click(prefix);
    expect(game.getAttribute("aria-checked")).toBe("mixed");
    fireEvent.click(cache);
    expect(game.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(prefix);
    expect(game.getAttribute("aria-checked")).toBe("mixed");
    fireEvent.click(cache);
    expect(game.getAttribute("aria-checked")).toBe("false");
  });

  it("keeps a prefix-only game active and opens its available data", () => {
    render(<SteamCleanerView controller={controller({ state: state({ entries: [entry("prefix", { kind: "compatdata" })] }) })} />);
    const game = screen.getByRole("button", { name: "cleaner.chooseGameData Game" });
    expect(game.getAttribute("aria-disabled")).toBe("false");
    expect((game.firstElementChild as HTMLElement).style.opacity).toBe("1");
    fireEvent.click(game);
    expect(screen.getByRole("checkbox", { name: "cleaner.kind.compatdata · Internal drive" })).toBeTruthy();
  });

  it("shows the storage explanation once and makes the recommended filter explicit", () => {
    render(<SteamCleanerView controller={controller({ state: state({ entries: [
      entry("installed", { game_id: "installed", name: "Installed" }),
      entry("recommended", { game_id: "recommended", name: "Recommended", installation: "not_installed" }),
      entry("prefix", { game_id: "installed", name: "Installed", kind: "compatdata" }),
    ] }) })} />);

    expect(screen.getAllByText("cleaner.cacheHint")).toHaveLength(1);
    expect(screen.getAllByText("cleaner.prefixHint")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.filterLabel" }));
    expect(screen.getByText("cleaner.filter.cleanable")).toBeTruthy();
    expect(screen.getByText("Installed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "cleaner.filterLabel" }));
    expect(screen.getByText("Recommended")).toBeTruthy();
    expect(screen.queryByText("Installed")).toBeNull();
  });

  it("keeps the storage explanation dismissed across mounts", () => {
    const view = render(<SteamCleanerView controller={controller()} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.help.dismiss" }));
    expect(screen.queryByText("cleaner.cacheHint")).toBeNull();
    view.unmount();
    render(<SteamCleanerView controller={controller()} />);
    expect(screen.queryByText("cleaner.cacheHint")).toBeNull();
  });

  it("explains when there are no recommended games", () => {
    render(<SteamCleanerView controller={controller()} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.filterLabel" }));
    fireEvent.click(screen.getByRole("button", { name: "cleaner.filterLabel" }));
    expect(screen.getByText("cleaner.noRecommendations")).toBeTruthy();
    expect(screen.queryByText("cleaner.noMatch")).toBeNull();
  });

  it("confirms prefixes inline while keeping the game list visible and selection locked", () => {
    const plan = { id: "one", scan_id: "scan", entries: [entry("prefix", { kind: "compatdata" })], estimated_bytes: 1_000_000, requires_prefix_confirmation: true, expires_at: 9999999999 };
    const c = controller({ plan });
    render(<SteamCleanerView controller={c} />);
    expect(screen.getByRole("button", { name: "cleaner.gameDetails Game" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "cleaner.selectCaches" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("cleaner.confirm.prefixWarning")).toBeTruthy();
    expect(c.execute).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "cleaner.confirm.delete" }));
    expect(c.execute).toHaveBeenCalledExactlyOnceWith(true);
  });

  it("lets the user leave the prefix warning without deleting data", () => {
    const c = controller({ plan: { id: "one", scan_id: "scan", entries: [entry("prefix", { kind: "compatdata" })], estimated_bytes: 1_000_000, requires_prefix_confirmation: true, expires_at: 9999999999 } });
    render(<SteamCleanerView controller={c} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.cancel" }));
    expect(c.dismissPlan).toHaveBeenCalledOnce();
    expect(c.execute).not.toHaveBeenCalled();
  });

  it("shows per-game partial failures using result metadata after the inventory changed", () => {
    const c = controller({ state: state({ scan_id: null, entries: [] }), result: { operation_id: "operation", cancelled: false, estimated_bytes_removed: 1_000_000, items: [
      { id: "removed", status: "deleted", bytes_removed: 1_000_000, reason: null, entry: { appid: "10", name: "Game", kind: "shadercache", library_label: "Internal drive" } },
      { id: "failed", status: "error", bytes_removed: 0, reason: "io_error", entry: { appid: "20", name: "Other Game", kind: "compatdata", library_label: "SD card" } },
    ] } });
    render(<SteamCleanerView controller={c} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.result.details" }));
    expect(screen.getByText("Game")).toBeTruthy();
    expect(screen.getByText("Other Game")).toBeTruthy();
    expect(screen.getByText(/cleaner.result.error · cleaner.reason.io_error/)).toBeTruthy();
    expect(screen.getByText("cleaner.result.estimate")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "cleaner.result.close" }));
    expect(c.dismissResult).toHaveBeenCalledOnce();
  });

  it("keeps only one cleanup action even with a long list", () => {
    render(<SteamCleanerView controller={controller({ state: state({ entries: Array.from({ length: 8 }, (_, index) => entry(`cache-${index}`, { game_id: `game-${index}`, appid: `${index + 10}` })) }) })} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.selectCaches" }));
    expect(screen.getAllByRole("button", { name: "cleaner.cleanSelection" })).toHaveLength(1);
  });

  it("can rescan after the cleanup result has been dismissed", () => {
    const c = controller({ state: state({ scan_id: null }), result: null });
    render(<SteamCleanerView controller={c} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.scanAfterCleanup" }));
    expect(c.scan).toHaveBeenCalledOnce();
    expect(screen.queryByText("cleaner.result.title")).toBeNull();
  });

  it("does not present unmeasured or unidentified game data as zero bytes or an AppID title", () => {
    render(<SteamCleanerView controller={controller({ state: state({ entries: [entry("unknown", { name: null, bytes: null, installation: "unknown", blocked_reason: "unknown_identity" })], totals: { shadercache: 0, compatdata: 0, unknown: 1 } }) })} />);
    const game = screen.getByRole("button", { name: "cleaner.chooseGameData cleaner.unknownGame" });
    expect(game.getAttribute("aria-disabled")).toBe("true");
    expect(within(game).getByText("cleaner.sizeUnknown")).toBeTruthy();
    expect(within(game).queryByText("0 B")).toBeNull();
    expect(screen.queryByText("AppID 10")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "cleaner.gameDetails cleaner.unknownGame" }));
    expect(screen.getByText("cleaner.steamIdentifier 10")).toBeTruthy();
    expect(screen.getByText("cleaner.reason.unknown_identity")).toBeTruthy();
    expect(screen.queryByText("cleaner.warning.unknown_identity")).toBeNull();
    expect(screen.getByRole("checkbox", { name: "cleaner.kind.shadercache · Internal drive" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("warns about an unidentified eligible game without claiming its data will be kept", () => {
    render(<SteamCleanerView controller={controller({ state: state({ entries: [entry("unknown", { name: null, installation: "not_installed", warnings: ["unknown_identity"] })] }) })} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.gameDetails cleaner.unknownGame" }));
    expect(screen.getByText("cleaner.warning.unknown_identity")).toBeTruthy();
    expect(screen.queryByText("cleaner.reason.unknown_identity")).toBeNull();
    const cache = screen.getByRole("checkbox", { name: "cleaner.kind.shadercache · Internal drive" });
    expect(cache.getAttribute("aria-disabled")).toBe("false");
    fireEvent.click(cache);
    expect(cache.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText(/cleaner.recommendation.game_not_installed/)).toBeTruthy();
  });

  it.each([
    { library_internal: true, library_label: "Steam", expected: "cleaner.internalStorage" },
    { library_internal: false, library_label: "SD card", expected: "SD card" },
    { library_label: "Steam", expected: "Steam" },
  ])("labels $library_label storage with internal=$library_internal in choices and results", ({ expected, ...library }) => {
    const cache = entry("cache", library);
    const c = controller({ state: state({ entries: [cache] }) });
    const view = render(<SteamCleanerView controller={c} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.gameDetails Game" }));
    const choice = screen.getByRole("checkbox", { name: `cleaner.kind.shadercache · ${expected}` });
    expect(within(choice).getByText(expected)).toBeTruthy();
    view.rerender(<SteamCleanerView controller={controller({
      state: state({ scan_id: null, entries: [] }),
      result: { operation_id: "operation", cancelled: false, estimated_bytes_removed: 1_000_000, items: [
        { id: "cache", status: "deleted", bytes_removed: 1_000_000, reason: null, entry: { appid: "10", name: "Game", kind: "shadercache", ...library } },
      ] },
    })} />);
    fireEvent.click(screen.getByRole("button", { name: "cleaner.result.details" }));
    expect(screen.getByText(`cleaner.kind.shadercache · ${expected}`)).toBeTruthy();
  });

  it("shows unknown totals when an unavailable library prevents any measurement", () => {
    render(<SteamCleanerView controller={controller({ state: state({
      coverage_complete: false, entries: [], totals: { shadercache: 0, compatdata: 0, unknown: 0 },
      libraries: [{ id: "library", label: "Internal drive", available: false, reason: "library_unavailable" }],
    }) })} />);
    expect(screen.getAllByText("cleaner.sizeUnknown")).toHaveLength(2);
    expect(screen.queryByText("0 B")).toBeNull();
    expect(screen.getByText("cleaner.coverageIncomplete")).toBeTruthy();
  });

  it("shows zero totals when a complete scan finds no data", () => {
    render(<SteamCleanerView controller={controller({ state: state({ entries: [], totals: { shadercache: 0, compatdata: 0, unknown: 0 } }) })} />);
    expect(screen.getAllByText("0 B")).toHaveLength(2);
    expect(screen.queryByText("cleaner.sizeUnknown")).toBeNull();
  });

  it("keeps remaining data unselectable until the post-deletion scan", () => {
    render(<SteamCleanerView controller={controller({ state: state({ scan_id: null }) })} />);
    const bulk = screen.getByRole("button", { name: "cleaner.selectCaches" });
    expect(bulk.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(bulk);
    expect(screen.queryByRole("button", { name: "cleaner.cleanSelection" })).toBeNull();
    expect(screen.getByRole("button", { name: "cleaner.scanAgain" })).toBeTruthy();
  });
});
