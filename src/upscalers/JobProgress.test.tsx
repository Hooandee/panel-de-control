// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { UpscalerJob } from "./types";

vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => params ? `${key} ${JSON.stringify(params)}` : key === "up.phase.verify" ? key : `[${key}]` }) }));
vi.mock("./parts", () => ({ Spinner: () => <i data-testid="spinner" /> }));
import { JobProgress } from "./JobProgress";

afterEach(cleanup);
const job = (phase: UpscalerJob["phase"], done = 0, total = 0) => ({ id: "j", appid: "1", kind: "install", state: "running", phase, done, total, error: null }) as UpscalerJob;
const bar = () => document.querySelector("[data-progress]")?.getAttribute("data-progress");

it.each(["prepare", "resolve", "dependencies", "unpack", "copy", "restore"] as const)("shows a spinner and an indeterminate bar while %s", (phase) => {
  render(<JobProgress job={job(phase)} />);
  expect(screen.getByTestId("spinner")).toBeTruthy();
  expect(screen.getByText(`[up.phase.${phase}]`)).toBeTruthy();
  expect(bar()).toBe("indeterminate");
});

it("does not count a download whose size is unknown", () => {
  render(<JobProgress job={job("download", 0, 0)} />);
  expect(screen.getByText("[up.phase.downloading]")).toBeTruthy();
  expect(screen.queryByText(/up.phase.download \{/)).toBeNull();
  expect(bar()).toBe("indeterminate");
});

it("measures a download of known size", () => {
  render(<JobProgress job={job("download", 1024 * 1024, 4 * 1024 * 1024)} />);
  expect(screen.getByText('up.phase.download {"done":"1","total":"4"}')).toBeTruthy();
  expect(bar()).toBe("determinate");
});


it("falls back to a generic step for a phase this version does not know", () => {
  render(<JobProgress job={job("verify" as UpscalerJob["phase"])} />);
  expect(screen.getByText("[up.phase.prepare]")).toBeTruthy();
});

it("brings itself into view when a job starts below the fold", () => {
  const scroll = vi.fn();
  const original = HTMLElement.prototype.scrollIntoView;
  HTMLElement.prototype.scrollIntoView = scroll;
  try {
    render(<JobProgress job={job("resolve")} />);
    expect(scroll).toHaveBeenCalledWith({ block: "nearest", behavior: "smooth" });
  } finally {
    HTMLElement.prototype.scrollIntoView = original;
  }
});
