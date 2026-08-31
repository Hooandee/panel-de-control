import {
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

const workspaces: string[] = [];
const verifier = resolve("scripts/verify-theme-pages-governance.mjs");
const repository = "Hooandee/panel-de-control";
const updatedAt = "2026-08-31T08:00:00Z";

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-theme-governance-"));
  workspaces.push(path);
  return path;
}

function ruleset(bypassActors = [{ actor_id: null, actor_type: "DeployKey", bypass_mode: "always" }]) {
  return {
    id: 42,
    name: "theme-pages-immutable",
    target: "branch",
    source_type: "Repository",
    source: repository,
    enforcement: "active",
    updated_at: updatedAt,
    bypass_actors: bypassActors,
    conditions: {
      ref_name: {
        include: ["refs/heads/gh-pages"],
        exclude: [],
      },
    },
    rules: ["creation", "update", "deletion", "non_fast_forward"].map((type) => ({ type })),
  };
}

function verifyGovernance({
  value = ruleset(),
  keys = [[{ id: 7, title: "theme-pages", read_only: false }, { id: 8, title: "reader", read_only: true }]],
}: {
  value?: ReturnType<typeof ruleset>;
  keys?: Array<Array<{ id: number; title: string; read_only: boolean }>>;
} = {}) {
  const root = workspace();
  const rulesetPath = resolve(root, "ruleset.json");
  const keysPath = resolve(root, "keys.json");
  writeFileSync(rulesetPath, JSON.stringify(value));
  writeFileSync(keysPath, JSON.stringify(keys));
  return spawnSync(process.execPath, [
    verifier,
    rulesetPath,
    keysPath,
    repository,
    "42",
    updatedAt,
    "7",
  ], { encoding: "utf8" });
}

describe("Pages publication governance", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("accepts the pinned ruleset with exactly its audited write deploy key", () => {
    expect(verifyGovernance()).toMatchObject({ status: 0, stderr: "" });
  });

  it("rejects another deploy key with write access even when the ruleset revision is unchanged", () => {
    const result = verifyGovernance({
      keys: [[
        { id: 7, title: "theme-pages", read_only: false },
        { id: 9, title: "unexpected-writer", read_only: false },
      ]],
    });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("exactly one audited write deploy key");
  });

  it("rejects any bypass actor outside the generic deploy-key actor required by GitHub", () => {
    const result = verifyGovernance({
      value: ruleset([
        { actor_id: null, actor_type: "DeployKey", bypass_mode: "always" },
        { actor_id: 99, actor_type: "Integration", bypass_mode: "always" },
      ]),
    });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("ruleset bypass actors are invalid");
  });
});
