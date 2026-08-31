import { createHash } from "node:crypto";
import {
  cpSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

const workspaces: string[] = [];
const sourcePin = resolve(
  process.cwd(),
  "themes/bundled/hooandee-gallery/0.7.8",
);

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-theme-copy-"));
  workspaces.push(path);
  return path;
}

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function copyPin(pin: string, output: string) {
  return spawnSync(process.execPath, [
    resolve(process.cwd(), "scripts/copy-bundled-theme.mjs"),
    pin,
    output,
  ], { encoding: "utf8" });
}

describe("bundled theme copy", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("copies the exact verified pin into a plugin package", () => {
    const output = workspace();

    const result = copyPin(sourcePin, output);

    expect(result).toMatchObject({ status: 0 });
    expect(readFileSync(resolve(output, "gallery.json")))
      .toEqual(readFileSync(resolve(sourcePin, "gallery.json")));
    expect(sha256(resolve(output, "gallery.zip")))
      .toBe(sha256(resolve(sourcePin, "gallery.zip")));
  });

  it("refuses a pin whose descriptor does not match its archive bytes", () => {
    const fixture = workspace();
    const pin = resolve(fixture, "pin");
    const output = resolve(fixture, "output");
    cpSync(sourcePin, pin, { recursive: true });
    const descriptorPath = resolve(pin, "gallery.json");
    const descriptor = JSON.parse(readFileSync(descriptorPath, "utf8")) as {
      artifact: { size: number };
    };
    descriptor.artifact.size += 1;
    writeFileSync(descriptorPath, `${JSON.stringify(descriptor, null, 2)}\n`);

    const result = copyPin(pin, output);

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("does not match its descriptor");
  });
});
