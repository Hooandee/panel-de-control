import catalog from "../../shared/upscalers/tested-profiles.json";
import { buildBlocker, supportsDllTargets } from "./model";
import type { BuildInfo, GameDetail, UpscalersOverview } from "./types";

type TestedModel = { build: string; model: string | null };
export type TestedDefault = (TestedModel & { mode: "dll" | "optiscaler" }) | { mode: "mako"; render?: number[] };

interface Route {
  input?: string;
  menuName?: string;
  menuEngine?: string;
  dependency?: string;
  userFile?: string;
  modRelease?: string;
  fixedQuality?: boolean;
  requiresTemporalInput?: boolean;
  proxy?: string;
  api?: string;
  exe?: string;
  requiresDx12Config?: boolean;
  signedOnly?: boolean;
  installedOptiScaler?: string;
}

interface DeviceProfile extends Route {
  gpu: string;
  build?: string;
  model?: string | null;
  mode?: string;
  output?: number[];
  render?: number[];
}

interface GameGuidance extends Route {
  name: string;
  profiles: Partial<Record<string, DeviceProfile>>;
}

const games: Partial<Record<string, GameGuidance>> = catalog;

export function gameUpscalerGuidance(detail: GameDetail | null, appid: string, device?: string): GameGuidance | undefined {
  if (!detail || detail.native || (detail.shortcut && !detail.identity?.steam_appid)) return;
  const game = games[String(detail.identity?.steam_appid ?? appid)];
  return game && { ...game, ...game.profiles[device ?? ""] };
}

function hasInput(guide: GameGuidance, detail: GameDetail, build: BuildInfo): boolean {
  const plan = detail.solutions?.[build.id];
  const inputs: Record<string, string[] | undefined> = plan?.inputs ?? detail.analysis.inputs;
  if (guide.dependency && (!plan?.input_reconciled || !plan.dependencies.includes(guide.dependency))) return false;
  if (guide.requiresTemporalInput && !["dlss", "fsr31", "fsr2", "xess"].some(key => inputs[key]?.length)) return false;
  return !guide.input || !!inputs[guide.input]?.length;
}

export function detectedGameInput(guide: GameGuidance, detail: GameDetail, build: BuildInfo): string | null {
  if (!guide.menuName || !detail.analysis.target || (build.engine ?? "optiscaler") !== (guide.menuEngine ?? "optiscaler")
    || detail.recipe_info?.luma_detected || detail.recipe_info?.automatic?.includes("Luma")) return null;
  return hasInput(guide, detail, build) ? guide.menuName : null;
}

export function needsManualGameConfig(detail: GameDetail): boolean {
  return detail.shortcut || detail.recipe_info?.game_config_matches !== true;
}

type Hardware = Pick<UpscalersOverview, "preferred" | "builds" | "device" | "gpu" | "display">;

export function initialBuild(preferred: string, tested?: TestedDefault): string {
  if (!tested || tested.mode === "mako" || tested.model !== "lite") return preferred;
  const preferLite = preferred === "fsr-4.1.1" || preferred === "fsr-4.1.2-beta";
  return preferLite && tested.build.startsWith("fsr-4.1.2") ? tested.build : preferred;
}

export function testedDefault(detail: GameDetail | null, appid: string, overview: Hardware, makoAvailable = false, reshadeRedirected = false): TestedDefault | undefined {
  const guide = gameUpscalerGuidance(detail, appid, overview.device);
  const tested = guide?.profiles[overview.device ?? ""];
  if (!detail?.analysis.target || !guide || !tested || tested.gpu !== overview.gpu || detail.recipe_info?.broken) return;
  if (tested.mode === "mako") {
    if (makoAvailable && !detail.analysis.foreign && tested.output?.every((pixels, i) => pixels === overview.display?.[i])) return { mode: "mako", render: tested.render };
    return;
  }
  if (!tested.build || tested.model === undefined) return;
  if (detail.analysis.anti_cheat_kind === "signed_only" && tested.build !== detail.preferred) return;
  const build = (detail.builds ?? overview.builds).find(({ id }) => id === tested.build);
  if (!build?.available || !build.supported || detail.failed_builds?.some(({ build }) => build === tested.build)) return;
  if (detail.install?.build === tested.build && detail.install.status === "broken") return;
  if (tested.model !== null ? !build.models?.includes(tested.model) : build.models?.length) return;
  const mode = build.engine ?? "optiscaler";
  if (mode !== "optiscaler" && mode !== "dll") return;
  if (mode === "dll" && !supportsDllTargets(build, detail.analysis.dll_targets ?? [])) return;
  const plan = detail.solutions?.[build.id];
  if (plan?.blocked_reason || plan?.warning_reason === "recipe_api_conflict" || detail.recipe_info?.blocked
    || buildBlocker(build, plan?.inputs ?? detail.analysis.inputs) || !hasInput(guide, detail, build)) return;
  if (guide.menuName && mode === "optiscaler" && !detectedGameInput(guide, detail, build)) return;
  if (guide.installedOptiScaler) {
    const install = detail.install;
    const release = install?.components?.find(component => component.id === install.archive)?.version;
    if (install?.build !== tested.build || release?.match(/\d+\.\d+\.\d+/)?.[0] !== guide.installedOptiScaler) return;
  }
  if (guide.signedOnly && detail.analysis.anti_cheat_kind !== "signed_only") return;
  if (guide.api && plan?.effective_api !== guide.api) return;
  if (guide.exe && detail.analysis.exe?.split("/").pop()?.toLowerCase() !== guide.exe) return;
  if (guide.proxy && detail.recipe_info?.proxy !== guide.proxy) return;
  if (guide.userFile && !detail.recipe_info?.user_files?.some(file => file.id === guide.userFile && file.state === "ready"
    && file.installed_version === file.version && plan?.dependencies.includes(file.id))) return;
  if (guide.modRelease && detail.mod?.tested_release !== guide.modRelease) return;
  if ((guide.dependency || guide.userFile) && reshadeRedirected) return;
  const components = detail.recipe_info?.windows_components;
  if (guide.dependency && detail.install && components && components !== "ready") return;
  if (guide.requiresDx12Config && needsManualGameConfig(detail)) return;
  return { mode, build: tested.build, model: tested.model };
}
