import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ installUpscaler: vi.fn(), uninstallUpscaler: vi.fn() }));
vi.mock("./jobRunner", () => ({ onJobUpdate: vi.fn(), trackJob: vi.fn() }));

import { bulkSteps } from "./bulk";
import { badgeLabel } from "./model";
import type { GameEntry } from "../launch/steamApi";
import type { UpscalersOverview } from "./types";

const game = (id: number, name: string) => ({ liveAppid: id, name, instanceKey: String(id), isNonSteam: false } as unknown as GameEntry);
const build = (id: string, engine: "optiscaler" | "proton" = "optiscaler") => ({
  id, family: "fsr" as const, version: "4.1.2", image: 3, cost: 2, available: true, supported: true, download_bytes: 0, engine,
});

const overview = {
  gpu: "rdna2", display: null, preferred: "fsr-new", cached: [], job: null,
  builds: [build("fsr-new"), build("fsr-old"), build("proton-4", "proton")],
  installs: {
    "1": { build: "fsr-old", proxy: "dxgi.dll", status: "loaded", options: { quality: "quality", sharpness: "high", fg: "on" } },
    "2": { build: "fsr-new", proxy: "dxgi.dll", status: "broken", options: { quality: null, sharpness: "soft" } },
    "3": { build: "proton-4", proxy: "", status: "broken" },
  },
} as unknown as UpscalersOverview;

const games = [game(1, "Old"), game(2, "Broken"), game(3, "Proton"), game(4, "Fresh"), game(5, "Linux"), game(6, "No inputs")];
const compat = { "4": { native: false, inputs: ["dlss"] }, "5": { native: true, inputs: [] }, "6": { native: false, inputs: [] } };

describe("bulk actions", () => {
  it("installs only where it can and never over another install", () => {
    expect(bulkSteps("install", games, overview, compat).map((s) => s.game.name)).toEqual(["Fresh"]);
    expect(bulkSteps("install", games, overview, compat)[0].choice).toMatchObject({ build: "fsr-new", quality: "native" });
  });

  it("moves to the recommended build keeping each game's options", () => {
    const steps = bulkSteps("update", games, overview, compat);
    expect(steps.map((s) => s.game.name)).toEqual(["Old"]);
    expect(steps[0].choice).toMatchObject({ build: "fsr-new", quality: "quality", sharpness: "high", fg: "on" });
  });

  it("repairs broken OptiScaler installs only and removes every install", () => {
    expect(bulkSteps("repair", games, overview, compat).map((s) => s.game.name)).toEqual(["Broken"]);
    expect(bulkSteps("remove", games, overview, compat).map((s) => s.game.name)).toEqual(["Old", "Broken", "Proton"]);
  });
});

describe("badge label", () => {
  it("names the Lite model unless the full one runs, and shortens for small tiles", () => {
    const fsr = { family: "fsr" as const, version: "4.1.2", models: ["lite", "full"] };
    expect(badgeLabel(fsr, null, "x")).toEqual({ full: "FSR 4.1.2 Lite", short: "FSR 4 Lite" });
    expect(badgeLabel(fsr, "full", "x")).toEqual({ full: "FSR 4.1.2", short: "FSR 4" });
    expect(badgeLabel(undefined, null, "fsr-gone")).toEqual({ full: "fsr-gone", short: "fsr-gone" });
  });
});
