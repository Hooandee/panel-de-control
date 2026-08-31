import { existsSync, readFileSync } from "node:fs";
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
  readPackageVersion(
    readFileSync(resolve(repository, "package.json"), "utf8"),
    "current",
  );
  for (const path of REQUIRED_RELEASE_PATHS) {
    if (!existsSync(resolve(repository, path))) {
      fail(`current Panel source does not include remote themes: ${path}`);
    }
  }

  const listedTags = git(repository, ["tag", "--list", "panel-de-control-v*"]);
  if (listedTags.status !== 0) fail("Panel release tags are unavailable");
  const candidates = listedTags.stdout
    .split("\n")
    .map((tag) => ({ tag, version: tag.replace(/^panel-de-control-v/, "") }))
    .filter(({ tag, version }) => tag && STABLE_SEMVER.test(version))
    .sort((left, right) => {
      const a = left.version.split(".").map(Number);
      const b = right.version.split(".").map(Number);
      return a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
    });

  for (const { tag, version } of candidates) {
    const taggedCommit = git(repository, [
      "rev-parse",
      "--verify",
      "--quiet",
      `refs/tags/${tag}^{commit}`,
    ]);
    if (taggedCommit.status !== 0) continue;
    if (git(repository, ["merge-base", "--is-ancestor", taggedCommit.stdout.trim(), "HEAD"]).status !== 0) {
      continue;
    }
    const taggedPackage = git(repository, ["show", `${tag}:package.json`]);
    if (taggedPackage.status !== 0) continue;
    let taggedVersion;
    try {
      taggedVersion = readPackageVersion(taggedPackage.stdout, "published");
    } catch {
      continue;
    }
    if (taggedVersion !== version) continue;
    if (REQUIRED_RELEASE_PATHS.every(
      (path) => git(repository, ["cat-file", "-e", `${tag}:${path}`]).status === 0,
    )) {
      return version;
    }
  }
  fail("no published Panel release includes remote themes");
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
