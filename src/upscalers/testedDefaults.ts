import { buildBlocker } from "./model";
import type { BuildInfo, GameDetail, UpscalersOverview } from "./types";

export type TestedModel = { build: string; model: string | null };

interface TestedPackage extends TestedModel {
  device: string;
  gpu: string;
  requiresDx12Config?: boolean;
}

interface GameGuidance {
  input: "dlss" | "fsr31" | "fsr2";
  menuName: string;
  requiredDependency?: string;
  tested: readonly TestedPackage[];
}

const steamMachine = { device: "steam_machine", gpu: "rdna3", build: "fsr-4.1.1", model: null } as const;
const steamDeckLcdLite = { device: "steam_deck_lcd", gpu: "rdna2", build: "fsr-4.1.2-beta", model: "lite" } as const;

const GUIDANCE: Readonly<Partial<Record<string, GameGuidance>>> = {
  "1151640": { input: "dlss", menuName: "NVIDIA DLSS", requiredDependency: "hzd-dlss-unlocker", tested: [steamMachine, steamDeckLcdLite] },
  "2420110": { input: "fsr31", menuName: "AMD FSR 3", tested: [steamMachine] },
  "1174180": { input: "fsr2", menuName: "AMD FSR 2.0", tested: [{ ...steamMachine, requiresDx12Config: true }] },
};

export function gameUpscalerGuidance(detail: GameDetail | null, appid: string): GameGuidance | undefined {
  if (!detail || detail.native || (detail.shortcut && !detail.identity?.steam_appid)) return;
  return GUIDANCE[String(detail.identity?.steam_appid ?? appid)];
}

export function detectedGameInput(guide: GameGuidance, detail: GameDetail, build: BuildInfo): string | null {
  if (!detail.analysis.target || (build.engine ?? "optiscaler") !== "optiscaler" || detail.recipe_info?.luma_detected || detail.recipe_info?.automatic?.includes("Luma")) return null;
  const solution = detail.solutions?.[build.id];
  const inputs = solution?.inputs ?? detail.analysis.inputs;
  if (!inputs[guide.input]?.length) return null;
  if (guide.requiredDependency && (!solution?.input_reconciled || !solution.dependencies.includes(guide.requiredDependency))) return null;
  return guide.menuName;
}

export function needsManualGameConfig(detail: GameDetail): boolean {
  return detail.shortcut || !detail.recipe_info?.game_config
    || !!detail.install?.game_config?.some(({ state }) => state === "missing" || state === "failed");
}

export function testedDefault(detail: GameDetail | null, appid: string, overview: UpscalersOverview): TestedModel | undefined {
  const guide = gameUpscalerGuidance(detail, appid);
  if (!detail || !guide) return;
  const preferred = detail.preferred ?? overview.preferred;
  const tested = guide.tested.find(({ device, gpu, build }) => device === overview.device && gpu === overview.gpu && build === preferred);
  if (!tested) return;
  const build = (detail.builds ?? overview.builds).find(({ id }) => id === tested.build);
  if (!build?.available || !build.supported || detail.failed_builds?.some(({ build }) => build === tested.build)) return;
  const plan = detail.solutions?.[build.id];
  const inputs = plan?.inputs ?? detail.analysis.inputs;
  if (plan?.blocked_reason || buildBlocker(build, inputs) || !detectedGameInput(guide, detail, build)) return;
  if (tested.requiresDx12Config) {
    const forcesDx12 = plan?.api_source === "recipe" && plan.effective_api === "d3d12";
    if (detail.shortcut || (needsManualGameConfig(detail) && !forcesDx12)) return;
  }
  if ((build.models?.[0] ?? null) !== tested.model) return;
  return { build: tested.build, model: tested.model };
}
