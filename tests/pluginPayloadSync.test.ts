import {
  mkdtempSync,
  mkdirSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

const workspaces: string[] = [];
const syncer = resolve("scripts/sync-plugin-payload.sh");

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-plugin-sync-"));
  workspaces.push(path);
  return path;
}

function write(path: string, contents: string): void {
  mkdirSync(resolve(path, ".."), { recursive: true });
  writeFileSync(path, contents);
}

function files(root: string, relative = ""): string[] {
  const directory = resolve(root, relative);
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = relative ? `${relative}/${entry.name}` : entry.name;
    return entry.isDirectory() ? files(root, path) : [path];
  });
}

describe("device plugin payload synchronization", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("makes an existing plugin directory exactly match the staged payload", () => {
    const root = workspace();
    const source = resolve(root, "source");
    const destination = resolve(root, "destination");
    write(resolve(source, "dist/index.js"), "current bundle\n");
    write(resolve(source, "main.py"), "current backend\n");
    write(resolve(destination, "dist/index.js"), "old bundle\n");
    write(resolve(destination, "dist/index.js.map"), "private source map\n");
    write(resolve(destination, "py_modules/__pycache__/old.pyc"), "old bytecode\n");
    write(resolve(destination, "._main.py"), "old metadata\n");

    const result = spawnSync("bash", [syncer, source, destination], { encoding: "utf8" });

    expect(result).toMatchObject({ status: 0, stderr: "" });
    expect(files(destination).sort()).toEqual(["dist/index.js", "main.py"]);
  });
});
