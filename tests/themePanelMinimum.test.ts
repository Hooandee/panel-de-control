import {
  mkdtempSync,
  mkdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

const workspaces: string[] = [];
const resolver = resolve("scripts/resolve-theme-panel-minimum.mjs");

function git(repository: string, ...args: string[]): void {
  const result = spawnSync("git", args, { cwd: repository, encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(result.stderr || `git ${args.join(" ")} failed`);
  }
}

function writeThemeCapability(repository: string): void {
  mkdirSync(resolve(repository, "py_modules"), { recursive: true });
  mkdirSync(resolve(repository, "src/themes"), { recursive: true });
  writeFileSync(resolve(repository, "py_modules/theme_remote_contract.py"), "SCHEMA_VERSION = 1\n");
  writeFileSync(resolve(repository, "src/themes/remotePublicationClient.ts"), "export const schemaVersion = 1;\n");
  writeFileSync(resolve(repository, "src/themes/panelThemeInstaller.ts"), "export const installerVersion = 1;\n");
}

function repository({ capabilityInRelease }: { capabilityInRelease: boolean }): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-theme-panel-minimum-"));
  workspaces.push(path);
  git(path, "init", "--quiet");
  git(path, "config", "user.name", "Panel tests");
  git(path, "config", "user.email", "panel-tests@example.invalid");
  writeFileSync(resolve(path, "package.json"), '{"version":"0.38.0"}\n');
  if (capabilityInRelease) writeThemeCapability(path);
  git(path, "add", ".");
  git(path, "commit", "--quiet", "-m", "release");
  git(path, "tag", "panel-de-control-v0.38.0");
  return path;
}

function resolveMinimum(repositoryPath: string) {
  return spawnSync(process.execPath, [resolver, repositoryPath], { encoding: "utf8" });
}

describe("published Panel minimum for remote themes", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("returns a released Panel version whose tag contains the remote theme capability", () => {
    const result = resolveMinimum(repository({ capabilityInRelease: true }));

    expect(result.status).toBe(0);
    expect(result.stdout).toBe("0.38.0\n");
    expect(result.stderr).toBe("");
  });

  it("rejects a current tree that added theme support after its only release", () => {
    const path = repository({ capabilityInRelease: false });
    writeThemeCapability(path);
    git(path, "add", ".");
    git(path, "commit", "--quiet", "-m", "add themes after release");

    const result = resolveMinimum(path);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("no published Panel release includes remote themes");
  });

  it("keeps the first compatible release as the minimum after unrelated Panel releases", () => {
    const path = repository({ capabilityInRelease: true });
    writeFileSync(resolve(path, "package.json"), '{"version":"0.39.0"}\n');
    git(path, "add", "package.json");
    git(path, "commit", "--quiet", "-m", "release unrelated Panel changes");
    git(path, "tag", "panel-de-control-v0.39.0");

    const result = resolveMinimum(path);

    expect(result.status).toBe(0);
    expect(result.stdout).toBe("0.38.0\n");
  });
});
