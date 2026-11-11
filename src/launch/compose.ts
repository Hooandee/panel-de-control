// Launch-options token engine. Pure (no @decky imports) so it's unit-testable.
//
// Steam's launch-options field is modeled as three zones around the %command%
// token, which stands for the game's real executable + its own args:
//
//     [ env vars ][ wrappers ]  %command%  [ suffix args ]
//
// - env vars (NAME=value) and wrappers (mangohud, gamemoderun, ~/lsfg, …) run
//   BEFORE the token, left→right (each wraps the next).
// - args after the token are appended to the game's own command line.
// - no %command% → the whole string is args (suffix); to add any env/wrapper we
//   must introduce the token (see serialize).
//
// This engine only splits/joins and adds/removes tokens by identity. It knows
// nothing about specific pills — the catalog maps pills onto these primitives, so
// anything we don't own (e.g. an EmuDeck/SRM string) is preserved verbatim.

export interface EnvVar {
  name: string;
  value: string;
}

export interface Parsed {
  envs: EnvVar[];
  wrappers: string[];
  suffix: string[];
  /** Whether the source string contained a %command% token. */
  hasCommand: boolean;
  /** More than one %command% (or otherwise ambiguous) → do not mutate. */
  malformed: boolean;
  /** The original source string, verbatim — returned as-is when malformed. */
  raw: string;
  /** Unifideck's `store:game_id` token: its launcher only honours variables written after it. */
  envAfter?: string;
}

const COMMAND = "%command%";
const ENV_RE = /^[A-Za-z_][A-Za-z0-9_]*=/;
// From Unifideck's launch options guide: `<id> VAR=value` works, `VAR=value %command% <id>` can lose the variable,
// and a bare `%command% <id>` does not launch.
const UNIFIDECK_ID_RE = /^(?:epic|gog|amazon|ubisoft|battlenet|microsoft|gamevault|itch):[A-Za-z0-9][A-Za-z0-9._-]*$/;

/** Split on whitespace but keep quoted substrings and backslash-escaped characters
 *  (including escaped whitespace, e.g. `hello\ world`) intact, so a value never
 *  gets split mid-token and re-joined into a corrupt command. */
function tokenize(s: string): { tokens: string[]; unbalanced: boolean } {
  const tokens: string[] = [];
  let cur = "";
  let quote: string | null = null;
  let escaped = false;
  for (const ch of s.trim()) {
    if (escaped) {
      cur += ch;
      escaped = false;
    } else if (ch === "\\") {
      cur += ch;
      escaped = true;
    } else if (quote) {
      cur += ch;
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") {
      cur += ch;
      quote = ch;
    } else if (/\s/.test(ch)) {
      if (cur) {
        tokens.push(cur);
        cur = "";
      }
    } else {
      cur += ch;
    }
  }
  if (cur) tokens.push(cur);
  // A dangling quote or trailing backslash means we can't reason about the string.
  return { tokens, unbalanced: quote !== null || escaped };
}

// Shell operators / expansions our simple model can't safely rewrite around.
const SHELL_OPS_RE = /[;&|`<>$]|\$\(/;

function hasShellOperators(tokens: string[]): boolean {
  return tokens.some((token) => {
    const wine = /^WINEDLLOVERRIDES=(["'])[a-zA-Z0-9_.*=,;\s-]*\1$/.test(token);
    return SHELL_OPS_RE.test(wine ? token.replace(/;/g, "") : token);
  });
}

function toEnv(token: string): EnvVar {
  const eq = token.indexOf("=");
  return { name: token.slice(0, eq), value: token.slice(eq + 1) };
}

/** The one authority for serializing an env assignment (so the preview's token
 *  matching in catalog.ownedTokens can't drift from what serialize() emits). */
export function envToken(name: string, value: string): string {
  return `${name}=${value}`;
}

export function parse(str: string): Parsed {
  const raw = str ?? "";
  const { tokens, unbalanced } = tokenize(raw);
  const cmdCount = tokens.filter((t) => t === COMMAND).length;
  const rawCmdCount = (raw.match(/%command%/g) || []).length;
  const empty: Parsed = { envs: [], wrappers: [], suffix: [], hasCommand: false, malformed: false, raw };
  // Read-only (never mutate) when the string is beyond our simple 3-zone model:
  // dangling quote/escape, shell operators, more than one %command%, or a %command%
  // that isn't a standalone token (e.g. embedded in a quoted `sh -c "…%command%"`).
  if (unbalanced || /[\r\n]/.test(raw) || hasShellOperators(tokens) || cmdCount > 1 || rawCmdCount !== cmdCount) {
    return { ...empty, malformed: true };
  }

  const idx = tokens.indexOf(COMMAND);
  const prefix = idx < 0 ? [] : tokens.slice(0, idx);
  let suffix = tokens.slice(idx + 1);
  const envs: EnvVar[] = [];
  const wrappers: string[] = [];
  for (const tok of prefix) {
    if (ENV_RE.test(tok)) envs.push(toEnv(tok));
    else wrappers.push(tok);
  }
  const id = suffix.findIndex((tok) => UNIFIDECK_ID_RE.test(tok));
  if (id < 0) return { envs, wrappers, suffix, hasCommand: idx >= 0, malformed: false, raw };
  const after = suffix.slice(id + 1);
  for (const tok of after) if (ENV_RE.test(tok)) envs.push(toEnv(tok));
  suffix = [...suffix.slice(0, id + 1), ...after.filter((tok) => !ENV_RE.test(tok))];
  return { envs, wrappers, suffix, hasCommand: idx >= 0, malformed: false, raw, envAfter: suffix[id] };
}

export function serialize(p: Parsed): string {
  // A malformed string is never mutated — hand back exactly what we read.
  if (p.malformed) return p.raw;
  // Fully empty → clean empty string (never leave a bare "%command%").
  if (p.envs.length === 0 && p.wrappers.length === 0 && p.suffix.length === 0) return "";
  const parts: string[] = [];
  if (p.envAfter && p.suffix.includes(p.envAfter)) {
    const at = p.suffix.indexOf(p.envAfter);
    if (p.wrappers.length > 0) parts.push(...p.wrappers, COMMAND);
    parts.push(...p.suffix.slice(0, at + 1), ...p.envs.map((e) => envToken(e.name, e.value)), ...p.suffix.slice(at + 1));
    return parts.join(" ");
  }
  for (const e of p.envs) parts.push(envToken(e.name, e.value));
  parts.push(...p.wrappers);
  // Emit the token when anything must run before the game, or the source had it.
  if (p.hasCommand || p.envs.length > 0 || p.wrappers.length > 0) parts.push(COMMAND);
  parts.push(...p.suffix);
  return parts.join(" ");
}

// ---- Immutable token primitives (the catalog composes with these) ----------

export function getEnv(p: Parsed, name: string): string | null {
  const e = p.envs.find((v) => v.name === name);
  return e ? e.value : null;
}

export function setEnv(p: Parsed, name: string, value: string | null): Parsed {
  const envs = p.envs.filter((v) => v.name !== name);
  if (value !== null) envs.push({ name, value });
  return { ...p, envs };
}

export function hasWrapper(p: Parsed, token: string): boolean {
  return p.wrappers.includes(token);
}

// Armada's launcher hands off with os.execv, so a bare name after it ("gamemoderun")
// is never resolved through PATH and the game fails to start.
const EXEC_PATH_ONLY_LAUNCHERS = new Set(["armada-game-launch"]);

function execPathOnlyLauncherIndex(wrappers: string[]): number {
  return wrappers.findIndex((w) => EXEC_PATH_ONLY_LAUNCHERS.has(w.slice(w.lastIndexOf("/") + 1)));
}

/** Append a wrapper (kept if already present). Callers add known wrappers in
 *  their canonical outer→inner order, so appending yields the right chain while
 *  any pre-existing (unknown) wrapper stays outermost — except launchers that only
 *  exec absolute paths, which must stay inside every wrapper we add. */
export function addWrapper(p: Parsed, token: string): Parsed {
  const launcher = execPathOnlyLauncherIndex(p.wrappers);
  const existing = p.wrappers.indexOf(token);
  if (launcher < 0 || (existing >= 0 && existing < launcher)) {
    return existing >= 0 ? p : { ...p, wrappers: [...p.wrappers, token] };
  }
  const others = p.wrappers.filter((w) => w !== token);
  const at = execPathOnlyLauncherIndex(others);
  return { ...p, wrappers: [...others.slice(0, at), token, ...others.slice(at)] };
}

export function removeWrapper(p: Parsed, token: string): Parsed {
  return { ...p, wrappers: p.wrappers.filter((w) => w !== token) };
}

export function hasArg(p: Parsed, flag: string): boolean {
  return p.suffix.includes(flag);
}

export function addArg(p: Parsed, flag: string): Parsed {
  if (p.suffix.includes(flag)) return p;
  return { ...p, suffix: [...p.suffix, flag] };
}

export function removeArg(p: Parsed, flag: string): Parsed {
  return { ...p, suffix: p.suffix.filter((a) => a !== flag) };
}
