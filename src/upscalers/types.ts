export type UpscalerStatus = "active" | "pending" | "loaded" | "not_run" | "broken";
export type Quality = "quality" | "balanced" | "performance" | "ultra";
export type Sharpness = "off" | "soft" | "high";
export type EasyMode = "image" | "balanced" | "fps";

export interface BuildInfo {
  id: string;
  family: "fsr" | "xess" | "helixsr";
  version: string;
  image: number;
  cost: number;
  available: boolean;
  channel?: "stable" | "beta";
  supported: boolean;
  download_bytes: number;
  models?: string[];
  engine?: "optiscaler" | "helixsr";
  way?: "fsr" | "scaler" | null;
}

export interface UpscalerJob {
  id: string;
  kind: "install" | "uninstall";
  appid: string;
  state: "running" | "done" | "error";
  phase: "prepare" | "download" | "unpack" | "build" | "copy" | "restore" | "done";
  step?: string | null;
  detail?: string | null;
  done: number;
  total: number;
  error: string | null;
  result?: { overrides?: string[]; args?: string[]; kept?: string[]; launcher?: "heroic" | "lutris" };
}

export interface UpscalersOverview {
  gpu: string;
  display: [number, number] | null;
  preferred: string;
  builds: BuildInfo[];
  cached: string[];
  installs: Record<string, { build: string; proxy: string; status: UpscalerStatus }>;
  job: UpscalerJob | null;
  helixsr?: { downloaded: boolean };
}

export type FgRoute = "game" | "optiscaler";

export interface FgPlan {
  input: string;
  output: string;
  source: FgRoute;
  experimental: boolean;
  follows_game?: boolean;
  route?: FgRoute;
  routes?: Partial<Record<FgRoute, unknown>>;
}

export interface UpscalerChoice {
  build: string;
  quality: Quality | null;
  sharpness: Sharpness | null;
  fg?: "on" | "off";
  fg_route?: FgRoute | null;
  model?: string | null;
  confirm_anti_cheat?: boolean;
  accept_nvidia?: boolean;
}

export interface HistoryEntry {
  build: string;
  proxy: string;
  at: number;
  result: UpscalerStatus;
  exe: string | null;
  facts?: { fg?: string; upscaler?: string; fsr4?: string; version?: string; resolution?: { render: number[]; output: number[] } };
}

export interface GameDetail {
  appid: string;
  name: string;
  updating: "running" | "pending" | null;
  analysis: {
    candidates: { exe: string; apis: string[] }[];
    exe: string | null;
    apis: string[];
    manual: boolean;
    target: string | null;
    inputs: Partial<Record<"fsr31" | "fsr2" | "dlss" | "xess" | "streamline", string[]>>;
    anti_cheat: boolean;
    foreign: boolean;
  };
  install: {
    build: string;
    proxy: string;
    exe: string | null;
    installed_at: number;
    options: { quality: Quality | null; sharpness: Sharpness | null; fg?: "on" | "off"; fg_route?: FgRoute | null; model?: string | null };
    status: UpscalerStatus;
  } | null;
  history: HistoryEntry[];
  recipe: boolean;
  recipe_info?: { needs: ("reframework" | "nvngx_dlss" | "anti_cheat_off")[]; broken: boolean; proxy: string | null; args: string[] } | null;
  fg_note?: "reflexOff" | null;
  launcher?: "heroic" | "lutris" | null;
  shortcut: boolean;
  native: boolean;
  fg_plan: FgPlan | null;
  identity: { steam_appid: number | null; name: string | null; source: string } | null;
}

export interface VerifyResult {
  result: UpscalerStatus;
  facts: HistoryEntry["facts"] & { present?: boolean };
}
