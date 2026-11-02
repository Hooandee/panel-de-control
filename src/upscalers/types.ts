export type UpscalerStatus = "active" | "pending" | "loaded" | "not_run" | "broken";
export type Quality = "quality" | "balanced" | "performance" | "ultra";
export type Sharpness = "off" | "soft" | "high";
export type EasyMode = "image" | "balanced" | "fps";

export interface BuildInfo {
  id: string;
  family: "fsr" | "xess";
  version: string;
  image: number;
  cost: number;
  available: boolean;
  supported: boolean;
  download_bytes: number;
}

export interface UpscalerJob {
  id: string;
  kind: "install" | "uninstall";
  appid: string;
  state: "running" | "done" | "error";
  phase: "prepare" | "download" | "copy" | "restore" | "done";
  done: number;
  total: number;
  error: string | null;
  result?: { override?: string; kept?: string[] };
}

export interface UpscalersOverview {
  gpu: string;
  preferred: string;
  builds: BuildInfo[];
  cached: string[];
  installs: Record<string, { build: string; proxy: string; status: UpscalerStatus }>;
  job: UpscalerJob | null;
}

export interface UpscalerChoice {
  build: string;
  quality: Quality | null;
  sharpness: Sharpness | null;
  confirm_anti_cheat?: boolean;
}

export interface HistoryEntry {
  build: string;
  proxy: string;
  at: number;
  result: UpscalerStatus;
  exe: string | null;
  facts?: { upscaler?: string; fsr4?: string; version?: string; resolution?: { render: number[]; output: number[] } };
}

export interface GameDetail {
  appid: string;
  name: string;
  updating: boolean;
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
    options: { quality: Quality | null; sharpness: Sharpness | null };
    status: UpscalerStatus;
  } | null;
  history: HistoryEntry[];
  override: string | null;
}

export interface VerifyResult {
  result: UpscalerStatus;
  facts: HistoryEntry["facts"] & { present?: boolean };
}
