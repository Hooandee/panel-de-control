import { describe, expect, it } from "vitest";
import fixture from "../../shared/fixtures/upscalers/launch_options.json";
import { applyLaunch, launchAfterJob, revertLaunch } from "../upscalers/model";

interface Case {
  id: string;
  op: "apply" | "revert" | "replace";
  input: { launch: string; args?: string[]; added?: string[]; removed?: string[] };
  expected: { value: string; added?: string[] } | null;
}

function run({ op, input }: Case): Case["expected"] {
  if (op === "apply") return applyLaunch(input.launch, [], input.args ?? []);
  if (op === "revert") {
    const value = revertLaunch(input.launch, [], input.added ?? []);
    return value === null ? null : { value };
  }
  const next = launchAfterJob(input.launch, { overrides: [], args: input.args, removed_overrides: [], removed_args: input.removed }, "install");
  return next ? { value: next.value, added: next.added } : null;
}

describe("shared launch options fixture", () => {
  for (const c of fixture.cases as Case[]) it(c.id, () => expect(run(c)).toEqual(c.expected));
});
