export type UpscalerStatus = "active" | "pending" | "loaded" | "not_run" | "broken";
export type Quality = "native" | "quality" | "balanced" | "performance" | "ultra";
export type Sharpness = "off" | "soft" | "high";

export interface BuildInfo {
  id: string;
  family: "fsr" | "xess" | "helixsr" | "proton";
  version: string;
  image: number;
  cost: number;
  available: boolean;
  channel?: "stable" | "beta";
  supported: boolean;
  download_bytes: number;
  dll_names?: string[];
  dll_legacy_names?: string[];
  models?: string[];
  engine?: "optiscaler" | "helixsr" | "proton" | "dll";
  way?: "fsr" | "scaler" | null;
  may_fallback?: string | null;
  /** Runs OptiScaler 10, so ANR FG can go in with it. */
  anr?: boolean;
}

export interface UpscalerJob {
  id: string;
  kind: "install" | "uninstall";
  appid: string;
  state: "running" | "done" | "error";
  phase: "prepare" | "resolve" | "dependencies" | "download" | "unpack" | "copy" | "restore" | "done";
  detail?: string | null;
  done: number;
  total: number;
  error: string | null;
  leftover?: { removed_overrides: string[]; removed_args: string[]; env: Record<string, string | null> };
  result?: {
    overrides?: string[]; args?: string[]; kept?: string[]; launcher?: "heroic" | "lutris" | "portproton";
    removed_overrides?: string[]; removed_args?: string[]; env?: Record<string, string | null>;
    /** Panel's own launch wrappers (the anti-cheat launcher swap a mod needs), placed before %command%. */
    wrappers?: string[];
  };
}

export interface UpscalersOverview {
  gpu: string;
  device?: string;
  display: [number, number] | null;
  preferred: string;
  /** The build ANR FG goes in with on this GPU; null where it is not offered. */
  anr_build?: string | null;
  builds: BuildInfo[];
  cached: string[];
  installs: Record<string, { build: string; proxy: string; status: UpscalerStatus; options?: Partial<UpscalerChoice>; fallback?: ScalerFallback | null;
    /** Frame generation the recipe turns on inside the user's mod (ERSS-FG). */
    mod_fg?: string | null }>;
  /** Mako and Lossless Scaling per game: they never show up as an install. */
  engines?: Record<string, {
    mako?: { spatial: boolean; fg: boolean; multiplier: number | null; engine?: 4 | 5 };
    lossless?: { multiplier: number | null };
  }>;
  job: UpscalerJob | null;
  helixsr?: { downloaded: boolean };
}

export type FgRoute = "game" | "optiscaler" | "anr";

export interface FgPlan {
  input: string;
  output: string;
  source: FgRoute;
  experimental: boolean;
  follows_game?: boolean;
  route?: FgRoute;
  routes?: Partial<Record<FgRoute, unknown>>;
}

export interface ResolvedSolution {
  effective_api: "d3d11" | "d3d12" | "vulkan" | null;
  api_source: "recipe" | "detected" | "unknown";
  quality: { owner: "panel" | "game"; reason: string | null };
  fg_plan: FgPlan | null;
  offered_fg_plan?: FgPlan | null;
  warning_reason?: string | null;
  blocked_reason: string | null;
  dependencies: string[];
  recipe_revision: number | null;
  inputs?: Record<string, string[]>;
  input_reconciled?: boolean;
  recommended_input?: string | null;
}

export interface UpscalerChoice {
  build: string;
  quality: Quality | null;
  sharpness: Sharpness | null;
  fg?: "on" | "off";
  fg_route?: FgRoute | null;
  model?: string | null;
  confirm_anti_cheat?: boolean;
  env?: string;
}

/** FSR 4 was installed but the game's log shows another scaler (or a failed texture hand-off). */
export interface ScalerFallback {
  requested: string;
  observed: string | null;
  reason: "vulkan_textures" | "backend_changed";
}

export interface HistoryEntry {
  build: string;
  proxy: string;
  at: number;
  result: UpscalerStatus;
  exe: string | null;
  facts?: { fallback?: ScalerFallback; fg?: string; upscaler?: string; fsr4?: string; version?: string; resolution?: { render: number[]; output: number[] }; initial_resolution?: { render: number[]; output: number[] } };
}

/** A build that closed the game within the short window of a launch with Panel's injection active. */
export interface FailedBuild {
  build: string;
  version?: string | null;
  seconds?: number | null;
  at?: number;
}

export interface GameDetail {
  preferred?: string;
  failed_builds?: FailedBuild[];
  builds?: BuildInfo[];
  solution?: ResolvedSolution | null;
  solutions?: Record<string, ResolvedSolution>;
  appid: string;
  name: string;
  updating: "running" | "pending" | null;
  analysis: {
    dll_targets?: string[];
    candidates: { exe: string; apis: string[] }[];
    exe: string | null;
    apis: string[];
    manual: boolean;
    target: string | null;
    inputs: Partial<Record<"fsr31" | "fsr2" | "dlss" | "xess" | "streamline", string[]>>;
    anti_cheat: boolean;
    /** `signed_only`: the protection closes the game on unsigned code; `warn`: a plain anti-cheat. */
    anti_cheat_kind?: "signed_only" | "warn" | null;
    /** Engines that write nothing into the game and skip the warning when it comes from a recipe. */
    anti_cheat_exempt?: string[];
    foreign: boolean;
    foreign_identity?: { engine: "helixsr" | "optiscaler" | "unknown"; variant: "dlss" | "fsr" | "unknown"; evidence: string[]; manifest_error: boolean } | null;
  };
  install: {
    archive?: string;
    components?: { id: string; version?: string }[];
    build: string;
    proxy: string;
    exe: string | null;
    installed_at: number;
    anti_cheat_accepted?: boolean;
    options: { quality: Quality | null; sharpness: Sharpness | null; fg?: "on" | "off"; fg_route?: FgRoute | null; model?: string | null };
    status: UpscalerStatus;
    /** From the first launch after the quality last changed: whether the game asked OptiScaler for its size. */
    quality_check?: { result: "respected" | "ignored"; input: string | null; ratio: number } | null;
    /** Settings Panel set in the game's own config (RDR2's API); "missing" until the game wrote that file. */
    game_config?: { tag: string; state: "set" | "already" | "missing" | "failed" }[];
  } | null;
  history: HistoryEntry[];
  recipe: boolean;
  foreign_backup?: { at: number } | null;
  recipe_info?: RecipeInfo | null;
  fg_note?: "reflexOff" | null;
  launcher?: "heroic" | "lutris" | "portproton" | null;
  shortcut: boolean;
  native: boolean;
  fg_plan: FgPlan | null;
  identity: { steam_appid: number | null; name: string | null; source: string } | null;
  mod?: GameMod | null;
  mod_download?: string | null;
}

export interface VerifyResult {
  result: UpscalerStatus;
  facts: HistoryEntry["facts"] & { present?: boolean };
}

export interface IniKey {
  key: string;
  value: string;
  help: string[];
  choices: string[] | null;
  default: string | null;
  managed: boolean;
}

export interface IniSection {
  name: string;
  keys: IniKey[];
}

/** A file the recipe needs that only the user can download (e.g. from Nexus). */
export interface UserFile {
  id: string;
  name: string;
  page_url: string;
  download_url?: string;
  version: string;
  installed_version: string | null;
  filename: string | null;
  state: "missing" | "ready" | "avoid" | "other_version";
}

/** A mod the user brought for one game, installed beside the exe with OptiScaler. */
export interface GameMod {
  tested_release?: string;
  filename: string | null;
  count: number;
  files: string[];
  native_dlls: string[];
  applied: boolean;
  /** Removed here; its files stay in the game until the upscaler reinstalls. */
  removed?: boolean;
}

export interface UserFileCandidate {
  path: string;
  filename: string;
  version: string | null;
}

export interface RecipeInfo {
  user_files?: UserFile[];
  game_settings?: { setting: string; value: string }[];
  /** Panel sets a game setting itself on install (RDR2's API): the page only asks while it could not. */
  game_config?: boolean;
  game_config_matches?: boolean;
  anr_settings?: { setting: string; value: string }[];
  fps_counter?: boolean;
  quality_on_exit?: boolean;
  recommended_input?: "dlss" | "fsr31" | "fsr2" | "xess" | null;
  luma_detected?: boolean;
  windows_components?: "ready" | "missing" | "pending" | "unknown";
  automatic?: string[];
  automatic_builds?: string[];
  blocked?: boolean;
  needs: ("reframework" | "nvngx_dlss" | "anti_cheat_off" | "luma" | "mod")[];
  broken: boolean;
  proxy: string | null;
  args: string[];
  status?: "works" | "broken" | "partial" | null;
  inputs?: string[];
  linux?: boolean;
  optipatcher?: boolean;
  page?: string | null;
  settings?: Record<string, string>;
  suggestions?: Record<string, string>;
}
