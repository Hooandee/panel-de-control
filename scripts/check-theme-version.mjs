import { readFileSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { spawnSync } from "node:child_process";

function fail(message) {
  throw new Error(message);
}

function git(args) {
  return spawnSync("git", args, { encoding: "utf8" });
}

function parseVersion(value, label) {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(value);
  if (!match) fail(`${label} must use semantic versioning without a v prefix`);
  return {
    core: match.slice(1, 4).map(BigInt),
    prerelease: match[4]?.split(".") ?? [],
  };
}

function compareIdentifier(left, right) {
  const leftNumber = /^\d+$/.test(left) ? BigInt(left) : null;
  const rightNumber = /^\d+$/.test(right) ? BigInt(right) : null;
  if (leftNumber !== null && rightNumber !== null) {
    if (leftNumber < rightNumber) return -1;
    if (leftNumber > rightNumber) return 1;
    return 0;
  }
  if (leftNumber !== null) return -1;
  if (rightNumber !== null) return 1;
  return left.localeCompare(right, "en");
}

function compareVersions(leftValue, rightValue) {
  const left = parseVersion(leftValue, "current theme version");
  const right = parseVersion(rightValue, "base theme version");
  for (let index = 0; index < left.core.length; index += 1) {
    if (left.core[index] < right.core[index]) return -1;
    if (left.core[index] > right.core[index]) return 1;
  }
  if (left.prerelease.length === 0 || right.prerelease.length === 0) {
    return left.prerelease.length === right.prerelease.length ? 0 : left.prerelease.length === 0 ? 1 : -1;
  }
  const length = Math.max(left.prerelease.length, right.prerelease.length);
  for (let index = 0; index < length; index += 1) {
    if (left.prerelease[index] === undefined) return -1;
    if (right.prerelease[index] === undefined) return 1;
    const compared = compareIdentifier(left.prerelease[index], right.prerelease[index]);
    if (compared !== 0) return compared;
  }
  return 0;
}

function manifestVersion(content, label) {
  let manifest;
  try {
    manifest = JSON.parse(content);
  } catch {
    fail(`${label} is invalid JSON`);
  }
  if (!manifest || typeof manifest.version !== "string") fail(`${label} has no version`);
  parseVersion(manifest.version, `${label} version`);
  return manifest.version;
}

function main() {
  const [directoryArgument, base] = process.argv.slice(2);
  if (!directoryArgument || !base) fail("usage: check-theme-version.mjs <theme-directory> <base-commit>");
  if (/^0+$/.test(base)) return;
  const directory = resolve(directoryArgument);
  const repository = git(["rev-parse", "--show-toplevel"]);
  if (repository.status !== 0) fail("theme version check requires a git worktree");
  const local = relative(repository.stdout.trim(), directory).split(sep).join("/");
  if (!local || local.startsWith("../")) fail("theme directory must be inside the repository");

  const baseManifest = git(["show", `${base}:${local}/theme.json`]);
  if (baseManifest.status !== 0) return;
  const changed = git(["diff", "--quiet", base, "--", local]);
  if (changed.status === 0) return;
  if (changed.status !== 1) fail(changed.stderr.trim() || "theme diff could not be inspected");

  const currentVersion = manifestVersion(
    readFileSync(resolve(directory, "theme.json"), "utf8"),
    "current theme.json",
  );
  const previousVersion = manifestVersion(baseManifest.stdout, "base theme.json");
  if (compareVersions(currentVersion, previousVersion) <= 0) {
    fail(`theme content changed but version ${currentVersion} is not newer than ${previousVersion}`);
  }
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
