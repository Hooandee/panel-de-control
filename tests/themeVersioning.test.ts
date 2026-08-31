import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";


const workspaces: string[] = [];

function git(root: string, ...args: string[]) {
  return spawnSync("git", args, { cwd: root, encoding: "utf8" });
}

function fixture(version = "0.6.0"): string {
  const root = mkdtempSync(resolve(tmpdir(), "pdc-theme-version-"));
  workspaces.push(root);
  mkdirSync(resolve(root, "themes/gallery"), { recursive: true });
  writeFileSync(
    resolve(root, "themes/gallery/theme.json"),
    `${JSON.stringify({ version })}\n`,
  );
  writeFileSync(resolve(root, "themes/gallery/tokens.css"), ":root{}\n");
  git(root, "init", "-q");
  git(root, "config", "user.email", "test@example.invalid");
  git(root, "config", "user.name", "Theme Test");
  git(root, "add", ".");
  git(root, "commit", "-qm", "base");
  return root;
}

function check(root: string) {
  return spawnSync(process.execPath, [
    resolve(process.cwd(), "scripts/check-theme-version.mjs"),
    "themes/gallery",
    "HEAD",
  ], { cwd: root, encoding: "utf8" });
}

describe("theme version immutability", () => {
  afterEach(() => workspaces.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

  it("rejects changed theme content under an existing version", () => {
    const root = fixture();
    writeFileSync(resolve(root, "themes/gallery/tokens.css"), ":root{color:red}\n");

    const result = check(root);

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("version 0.6.0 is not newer than 0.6.0");
  });

  it("accepts changed content only after the theme version advances", () => {
    const root = fixture();
    writeFileSync(resolve(root, "themes/gallery/tokens.css"), ":root{color:red}\n");
    writeFileSync(resolve(root, "themes/gallery/theme.json"), '{"version":"0.6.1"}\n');

    expect(check(root).status).toBe(0);
  });

  it("orders arbitrarily large semantic version numbers exactly", () => {
    const root = fixture("9007199254740992.0.0");
    writeFileSync(resolve(root, "themes/gallery/tokens.css"), ":root{color:red}\n");
    writeFileSync(
      resolve(root, "themes/gallery/theme.json"),
      '{"version":"9007199254740993.0.0"}\n',
    );

    expect(check(root).status).toBe(0);
  });
});
