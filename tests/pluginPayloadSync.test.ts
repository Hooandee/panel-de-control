import {
  chmodSync,
  mkdtempSync,
  mkdirSync,
  readdirSync,
  rmSync,
  symlinkSync,
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
    const destinationRoot = resolve(root, "plugins");
    const destination = resolve(destinationRoot, "Panel de Control");
    write(resolve(source, "dist/index.js"), "current bundle\n");
    write(resolve(source, "main.py"), "current backend\n");
    write(resolve(destination, "dist/index.js"), "old bundle\n");
    write(resolve(destination, "dist/index.js.map"), "private source map\n");
    write(resolve(destination, "py_modules/__pycache__/old.pyc"), "old bytecode\n");
    write(resolve(destination, "._main.py"), "old metadata\n");

    const result = spawnSync("bash", [syncer, source, destination, destinationRoot], { encoding: "utf8" });

    expect(result).toMatchObject({ status: 0, stderr: "" });
    expect(files(destination).sort()).toEqual(["dist/index.js", "main.py"]);
  });

  it("refuses symlinked sources and destinations before exact synchronization", () => {
    const root = workspace();
    const source = resolve(root, "source");
    const destinationRoot = resolve(root, "plugins");
    const realDestination = resolve(root, "outside");
    const destination = resolve(destinationRoot, "Panel de Control");
    write(resolve(source, "main.py"), "current backend\n");
    write(resolve(realDestination, "keep.txt"), "must survive\n");
    mkdirSync(destinationRoot, { recursive: true });
    symlinkSync(realDestination, destination);

    const destinationResult = spawnSync(
      "bash",
      [syncer, source, destination, destinationRoot],
      { encoding: "utf8" },
    );

    expect(destinationResult.status).not.toBe(0);
    expect(files(realDestination)).toEqual(["keep.txt"]);

    rmSync(destination);
    const linkedSource = resolve(root, "linked-source");
    symlinkSync(source, linkedSource);
    mkdirSync(destination, { recursive: true });
    const sourceResult = spawnSync(
      "bash",
      [syncer, linkedSource, destination, destinationRoot],
      { encoding: "utf8" },
    );

    expect(sourceResult.status).not.toBe(0);
  });

  it("refuses destinations outside the declared plugin root", () => {
    const root = workspace();
    const source = resolve(root, "source");
    const destinationRoot = resolve(root, "plugins");
    const destination = resolve(root, "outside", "Panel de Control");
    write(resolve(source, "main.py"), "current backend\n");
    write(resolve(destination, "keep.txt"), "must survive\n");
    mkdirSync(destinationRoot, { recursive: true });

    const result = spawnSync(
      "bash",
      [syncer, source, destination, destinationRoot],
      { encoding: "utf8" },
    );

    expect(result.status).not.toBe(0);
    expect(files(destination)).toEqual(["keep.txt"]);
  });

  it("preserves an existing ryzenadj fallback when the local payload has no binary", () => {
    const root = workspace();
    const source = resolve(root, "source");
    const destinationRoot = resolve(root, "plugins");
    const destination = resolve(destinationRoot, "Panel de Control");
    write(resolve(source, "main.py"), "current backend\n");
    write(resolve(source, "bin/.gitkeep"), "");
    write(resolve(destination, "bin/ryzenadj"), "existing linux binary\n");
    chmodSync(resolve(destination, "bin/ryzenadj"), 0o755);
    write(resolve(destination, "bin/ryzenadj-LICENSE.txt"), "existing license\n");
    write(resolve(destination, "bin/stale-tool"), "remove me\n");

    const result = spawnSync(
      "bash",
      [syncer, source, destination, destinationRoot],
      { encoding: "utf8" },
    );

    expect(result).toMatchObject({ status: 0, stderr: "" });
    expect(files(destination).sort()).toEqual([
      "bin/.gitkeep",
      "bin/ryzenadj",
      "bin/ryzenadj-LICENSE.txt",
      "main.py",
    ]);
  });
});
