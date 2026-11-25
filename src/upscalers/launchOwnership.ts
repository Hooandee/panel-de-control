export interface LaunchReceipt {
  version: 1;
  pending?: boolean;
  env: { name: string; before: string | null; applied: string }[];
  wrappers: { before: string[]; applied: string[]; added: string[] };
}

export interface LaunchOverlay {
  env?: Record<string, string>;
  wrappers?: string[];
  replaceEnv?: string[];
}

export interface LaunchOverlayPlan {
  value: string;
  receipt: LaunchReceipt;
  preserved: { env: string[]; wrappers: string[] };
}

function equal(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, i) => value === b[i]);
}

/** Takes out the wrappers Panel added wherever they now sit; one the user gave its own options stays theirs. */
function withoutOwnedWrappers(current: string[], added: string[]): { wrappers: string[]; customized: string[]; missing: string[] } {
  let wrappers = [...current];
  const customized: string[] = [];
  const missing: string[] = [];
  for (const token of added) {
    const at = wrappers.indexOf(token);
    if (at < 0) missing.push(token);
    else if (wrappers[at + 1]?.startsWith("-")) customized.push(token);
    else wrappers = [...wrappers.slice(0, at), ...wrappers.slice(at + 1)];
  }
  return { wrappers, customized, missing };
}

function wrapperFamily(token: string): string {
  const parts = token.replace(/^(["'])(.*)\1$/, "$2").split("/");
  const name = parts[parts.length - 1];
  return ["mako-run", "mako-launch", "mako-framegen"].includes(name) ? "mako" : name;
}

function assign(parsed: Parsed, name: string, value: string | null): Parsed {
  if (value === null || getEnv(parsed, name) === null) return setEnv(parsed, name, value);
  return { ...parsed, envs: parsed.envs.map((e) => e.name === name ? { name, value } : e) };
}

function validEnv(name: string, value: string): boolean {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return false;
  const parsed = parse(`${name}=${value} %command%`);
  return !parsed.malformed && parsed.envs.length === 1 && parsed.envs[0].value === value && !parsed.wrappers.length && !parsed.suffix.length;
}

function validWrapper(token: string): boolean {
  const parsed = parse(`${token} %command%`);
  return !parsed.malformed && !parsed.envs.length && equal(parsed.wrappers, [token]) && !parsed.suffix.length;
}

/** Receipts persist private ownership intent; they do not prove Steam applied a write. Never include them in diagnostics. */
export function planLaunchOverlay(launch: string, desired: LaunchOverlay, previous?: LaunchReceipt | null): LaunchOverlayPlan | null {
  let parsed = parse(launch);
  if (parsed.malformed || new Set(parsed.envs.map((e) => e.name)).size !== parsed.envs.length) return null;
  if (Object.entries(desired.env ?? {}).some(([name, value]) => !validEnv(name, value)) || (desired.wrappers ?? []).some((token) => !validWrapper(token))) return null;
  const preserved: LaunchOverlayPlan["preserved"] = { env: [], wrappers: [] };
  if (previous) {
    if (previous.version !== 1 || previous.env.some((e) => !validEnv(e.name, e.applied) || (e.before !== null && !validEnv(e.name, e.before)))) return null;
    for (const entry of previous.env) {
      if (getEnv(parsed, entry.name) === entry.applied) parsed = assign(parsed, entry.name, entry.before);
      else if (!previous.pending || getEnv(parsed, entry.name) !== entry.before) preserved.env.push(entry.name);
    }
    if (previous.wrappers.added.length) {
      if (equal(parsed.wrappers, previous.wrappers.applied)) parsed = { ...parsed, wrappers: [...previous.wrappers.before] };
      else {
        const { wrappers, customized, missing } = withoutOwnedWrappers(parsed.wrappers, previous.wrappers.added);
        parsed = { ...parsed, wrappers };
        preserved.wrappers.push(...customized);
        if (missing.length && (!previous.pending || !equal(wrappers, previous.wrappers.before))) preserved.wrappers.push(...missing);
      }
    }
  }
  const receipt: LaunchReceipt = { version: 1, env: [], wrappers: { before: [...parsed.wrappers], applied: [], added: [] } };
  for (const [name, applied] of Object.entries(desired.env ?? {})) {
    if (preserved.env.includes(name)) continue;
    const before = getEnv(parsed, name);
    if (before === applied) continue;
    if (before !== null && !desired.replaceEnv?.includes(name)) {
      preserved.env.push(name);
      continue;
    }
    parsed = assign(parsed, name, applied);
    receipt.env.push({ name, before, applied });
  }
  for (const token of desired.wrappers ?? []) {
    const existing = parsed.wrappers.find((candidate) => wrapperFamily(candidate) === wrapperFamily(token));
    if (existing) {
      if (!preserved.wrappers.includes(existing)) preserved.wrappers.push(existing);
      continue;
    }
    if (preserved.wrappers.some((existing) => wrapperFamily(existing) === wrapperFamily(token))) continue;
    parsed = addWrapper(parsed, token);
    receipt.wrappers.added.push(token);
  }
  receipt.wrappers.applied = [...parsed.wrappers];
  const value = serialize(parsed);
  return { value: value === serialize(parse(launch)) ? launch : value, receipt, preserved };
}
import { addWrapper, getEnv, parse, serialize, setEnv, type Parsed } from "../launch/compose";

