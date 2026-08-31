import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const STABLE_SEMVER = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const REQUIRED_RELEASE_PATHS = [
  "py_modules/theme_remote_contract.py",
  "src/themes/remotePublicationClient.ts",
  "src/themes/panelThemeInstaller.ts",
];

function fail(message) {
  throw new Error(message);
}

function readPackageVersion(bytes, label) {
  let manifest;
  try {
    manifest = JSON.parse(bytes);
  } catch {
    fail(`${label} package.json is invalid`);
  }
  if (typeof manifest?.version !== "string" || !STABLE_SEMVER.test(manifest.version)) {
    fail(`${label} Panel version must be a stable semantic version`);
  }
  return manifest.version;
}

function git(repository, args) {
  return spawnSync("git", args, {
    cwd: repository,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

export function resolveThemePanelMinimum(repositoryDirectory) {
  const repository = resolve(repositoryDirectory);
  const version = readPackageVersion(
    readFileSync(resolve(repository, "package.json"), "utf8"),
    "current",
  );
  const tag = `panel-de-control-v${version}`;
  const taggedCommit = git(repository, [
    "rev-parse",
    "--verify",
    "--quiet",
    `refs/tags/${tag}^{commit}`,
  ]);
  if (taggedCommit.status !== 0) {
    fail(`published Panel release tag is missing: ${tag}`);
  }

  const taggedPackage = git(repository, ["show", `${tag}:package.json`]);
  if (taggedPackage.status !== 0) fail("published Panel release package is unavailable");
  if (readPackageVersion(taggedPackage.stdout, "published") !== version) {
    fail("published Panel release version does not match package.json");
  }

  for (const path of REQUIRED_RELEASE_PATHS) {
    if (git(repository, ["cat-file", "-e", `${tag}:${path}`]).status !== 0) {
      fail(`published Panel release does not include remote themes: ${path}`);
    }
  }
  return version;
}

function main() {
  const repository = process.argv[2] ?? process.cwd();
  process.stdout.write(`${resolveThemePanelMinimum(repository)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
