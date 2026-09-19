// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import type { CleanerController } from "./useSteamCleaner";
import type { MediaCleanerController } from "./useMediaCleaner";
import type { ProtonCleanerController } from "./useProtonCleaner";

vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Focusable: ({ children, onActivate: _activate, onCancel: _cancel, onOKActionDescription: _legend, "flow-children": _flow, ...props }: { children?: ReactNode; [key: string]: unknown }) => <div {...props}>{children}</div>,
  TextField: ({ label, value, onChange }: { label: string; value: string; onChange: (event: unknown) => void }) => <label>{label}<input value={value} onChange={onChange} /></label>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ lang: "es", t: (key: string, values?: Record<string, unknown>) => `${key}${values ? ` ${Object.values(values).join(" ")}` : ""}` }) }));
vi.mock("../system/pdcStorage", () => ({
  readFlag: () => false,
  writeFlag: vi.fn(),
  onPrefsHealed: () => () => {},
}));
vi.mock("./steamMetadata", () => ({
  readCleanerMetadata: () => new Map([["10", { name: "Game", coverUrls: [] }]]),
  readInstalledCleanerMetadata: () => [],
  readInstalledProtonMetadata: () => [{ appid: "100", name: "Proton 10" }],
}));
import { CleanupHubView } from "./CleanupHubView";

const games = (): CleanerController => ({
  state: { schema_version: 1, available: true, status: "ready", scan_id: "scan", coverage_complete: true, entries: [], libraries: [], totals: { shadercache: 10, compatdata: 20, unknown: 0 }, progress: { processed: 0, total: 0 }, error: null, last_result: null },
  plan: null, result: null, error: null, loading: false, pending: null, busy: false, cancelling: false,
  scan: vi.fn(async () => {}), prepare: vi.fn(async () => {}), execute: vi.fn(async () => {}), cancel: vi.fn(async () => {}), refresh: vi.fn(async () => {}), dismissPlan: vi.fn(), dismissResult: vi.fn(),
});
const media = (): MediaCleanerController => ({
  items: [{ id: "screenshot:10:7", kind: "screenshot", gameId: "10", handle: 7, clipId: null, title: null, thumbnailUrl: "shot.jpg", createdAt: 1, durationSeconds: null, width: 1280, height: 800, bytes: 40, path: "/shot.jpg", active: false, recommendation: "old_capture" }],
  loading: false, cleaning: false, busy: false, error: null, result: null,
  scan: vi.fn(async () => {}), clean: vi.fn(async () => {}), dismissResult: vi.fn(),
});
const proton = (): ProtonCleanerController => ({
  state: { schema_version: 1, available: true, status: "ready", scan_id: "proton", coverage_complete: true, entries: [{ id: "official", name: "Proton 10.0", tool_name: "proton_10", source: "steam", appid: "100", bytes: 50, status: "managed_by_steam", selectable: false, recommended: false, reason: "managed_by_steam" }], totals: { bytes: 50, unknown: 0 }, progress: { processed: 1, total: 1 }, error: null, last_result: null },
  loading: false, pending: null, busy: false, error: null, result: null,
  refresh: vi.fn(async () => {}), queueScan: vi.fn(), scan: vi.fn(async () => {}), clean: vi.fn(async () => {}), dismissResult: vi.fn(),
});

afterEach(cleanup);

it("keeps one understandable summary and persistent selections across tabs", () => {
  const mediaController = media();
  render(<CleanupHubView games={games()} media={mediaController} proton={proton()} onRefresh={vi.fn()} refreshing={false} />);

  expect(screen.getByRole("tab", { name: "cleaner.tab.games" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByText("30 B")).toBeTruthy();
  expect(screen.getAllByText("40 B").length).toBeGreaterThan(0);
  expect(screen.getAllByText("50 B").length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole("tab", { name: "cleaner.tab.media" }));
  const choice = screen.getByRole("checkbox", { name: "cleaner.media.select Game" });
  expect(choice.getAttribute("aria-checked")).toBe("false");
  expect(screen.getByText(/cleaner\.recommended/)).toBeTruthy();
  fireEvent.click(choice);
  expect(screen.getByRole("button", { name: "cleaner.media.clean" })).toBeTruthy();

  fireEvent.click(screen.getByRole("tab", { name: "cleaner.tab.games" }));
  expect(screen.queryByRole("button", { name: "cleaner.media.clean" })).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "cleaner.tab.media" }));
  fireEvent.click(screen.getByRole("button", { name: "cleaner.media.clean" }));
  expect(mediaController.clean).toHaveBeenCalledWith(["screenshot:10:7"]);
});

it("shows loading in each unfinished summary field without hiding the available totals", () => {
  const m = media();
  m.loading = true;
  const p = proton();
  p.loading = true;
  p.state = null;
  render(<CleanupHubView games={games()} media={m} proton={p} onRefresh={vi.fn()} refreshing />);

  expect(screen.getByText("30 B")).toBeTruthy();
  expect(screen.getAllByText("cleaner.calculating").filter((element) => !element.closest('[role="tabpanel"]'))).toHaveLength(2);
});

it("shows installed Proton tools while their sizes are calculated", () => {
  const p = proton();
  p.state = null;
  p.loading = true;
  render(<CleanupHubView games={games()} media={media()} proton={p} onRefresh={vi.fn()} refreshing={false} />);

  fireEvent.click(screen.getByRole("tab", { name: "cleaner.tab.proton" }));

  expect(screen.getByText("Proton 10")).toBeTruthy();
  expect(screen.getAllByText("cleaner.calculating").length).toBeGreaterThan(0);
});

it("shows an honest unknown total and warning when Proton coverage is incomplete", () => {
  const p = proton();
  if (!p.state) throw new Error("missing test state");
  p.state = { ...p.state, coverage_complete: false, totals: { bytes: 50, unknown: 1 } };
  render(<CleanupHubView games={games()} media={media()} proton={p} onRefresh={vi.fn()} refreshing={false} />);

  expect(screen.getByText("cleaner.sizeUnknown").style.fontSize).toBe("12px");
  fireEvent.click(screen.getByRole("tab", { name: "cleaner.tab.proton" }));
  expect(screen.getByText("cleaner.proton.coverageIncomplete")).toBeTruthy();
});

it("explains captures that Steam has not associated with a game", () => {
  const m = media();
  m.items = [{ ...m.items[0], gameId: "unmapped" }];
  render(<CleanupHubView games={games()} media={m} proton={proton()} onRefresh={vi.fn()} refreshing={false} />);

  fireEvent.click(screen.getByRole("tab", { name: "cleaner.tab.media" }));

  expect(screen.getByText("cleaner.media.unassociated")).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: "cleaner.media.select cleaner.media.unassociated" })).toBeTruthy();
});

it("does not present a partial media total as final", () => {
  const m = media();
  m.error = "media_incomplete";
  render(<CleanupHubView games={games()} media={m} proton={proton()} onRefresh={vi.fn()} refreshing={false} />);

  expect(screen.getByText("cleaner.sizeUnknown")).toBeTruthy();
});
