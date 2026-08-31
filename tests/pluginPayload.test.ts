import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

const workspaces: string[] = [];
const copier = resolve("scripts/copy-plugin-payload.mjs");

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-plugin-payload-"));
  workspaces.push(path);
  return path;
}

function write(path: string, contents = `${basename(path)}\n`): void {
  mkdirSync(resolve(path, ".."), { recursive: true });
  writeFileSync(path, contents);
}

function fixture({ symlink = false }: { symlink?: boolean } = {}): string {
  const root = workspace();
  write(resolve(root, "dist/index.js"), "plugin bundle\n");
  write(resolve(root, "dist/index.js.map"), "/Users/private/source.ts\n");
  for (const file of [
    "main.py",
    "plugin.json",
    "package.json",
    "README.md",
    "README.en.md",
    "LICENSE",
    "py_modules/module.py",
    "assets/icon.png",
    "bin/tool",
  ]) write(resolve(root, file));
  write(
    resolve(root, "py_modules/__pycache__/module.cpython-314.pyc"),
    "/Users/private/worktree/py_modules/module.py\n",
  );
  write(resolve(root, "py_modules/module.pyo"), "compiled\n");
  if (symlink) symlinkSync("tool", resolve(root, "bin/tool-link"));
  return root;
}

function files(root: string, relative = ""): string[] {
  const directory = resolve(root, relative);
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = relative ? `${relative}/${entry.name}` : entry.name;
    return entry.isDirectory() ? files(root, path) : [path];
  });
}

describe("plugin release payload", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("copies the installable payload without caches, source maps or private build paths", () => {
    const source = fixture();
    const output = resolve(workspace(), "Panel de Control");

    const result = spawnSync(process.execPath, [copier, source, output], { encoding: "utf8" });

    expect(result).toMatchObject({ status: 0, stderr: "" });
    expect(files(output)).toEqual(expect.arrayContaining([
      "dist/index.js",
      "main.py",
      "py_modules/module.py",
      "assets/icon.png",
      "bin/tool",
    ]));
    expect(files(output).some((path) => /(?:^|\/)__pycache__(?:\/|$)|\.(?:pyc|pyo|map)$/.test(path)))
      .toBe(false);
    expect(files(output).some((path) => readFileSync(resolve(output, path)).includes("/Users/")))
      .toBe(false);
    expect(existsSync(resolve(output, "py_modules/__pycache__"))).toBe(false);
  });

  it("rejects symlinks instead of copying content from an unreviewed target", () => {
    const source = fixture({ symlink: true });
    const output = resolve(workspace(), "Panel de Control");

    const result = spawnSync(process.execPath, [copier, source, output], { encoding: "utf8" });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("plugin payload symlink is not allowed");
    expect(existsSync(output)).toBe(false);
  });
});
