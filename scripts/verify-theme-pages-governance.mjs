import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const REQUIRED_RULES = new Set(["creation", "update", "deletion", "non_fast_forward"]);

function fail(message) {
  throw new Error(message);
}

function readJson(path, label) {
  try {
    return JSON.parse(readFileSync(resolve(path), "utf8"));
  } catch {
    fail(`${label} is invalid`);
  }
}

function positiveInteger(value, label) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number <= 0 || String(number) !== String(value)) {
    fail(`${label} is invalid`);
  }
  return number;
}

export function verifyThemePagesGovernance({
  ruleset,
  deployKeyPages,
  repository,
  rulesetId,
  rulesetUpdatedAt,
  deployKeyId,
}) {
  if (
    !ruleset
    || typeof ruleset !== "object"
    || Array.isArray(ruleset)
    || ruleset.id !== rulesetId
    || ruleset.updated_at !== rulesetUpdatedAt
    || ruleset.name !== "theme-pages-immutable"
    || ruleset.target !== "branch"
    || ruleset.source_type !== "Repository"
    || ruleset.source !== repository
    || ruleset.enforcement !== "active"
    || !Array.isArray(ruleset.conditions?.ref_name?.include)
    || ruleset.conditions.ref_name.include.length !== 1
    || ruleset.conditions.ref_name.include[0] !== "refs/heads/gh-pages"
    || !Array.isArray(ruleset.conditions?.ref_name?.exclude)
    || ruleset.conditions.ref_name.exclude.length !== 0
    || !Array.isArray(ruleset.rules)
    || ![...REQUIRED_RULES].every(
      (type) => ruleset.rules.some((rule) => rule?.type === type),
    )
  ) {
    fail("Pages ruleset contract is invalid");
  }

  if (
    !Array.isArray(ruleset.bypass_actors)
    || ruleset.bypass_actors.length !== 1
    || ruleset.bypass_actors[0]?.actor_id !== null
    || ruleset.bypass_actors[0]?.actor_type !== "DeployKey"
    || ruleset.bypass_actors[0]?.bypass_mode !== "always"
  ) {
    fail("ruleset bypass actors are invalid");
  }

  if (!Array.isArray(deployKeyPages) || !deployKeyPages.every(Array.isArray)) {
    fail("deploy key inventory is invalid");
  }
  const deployKeys = deployKeyPages.flat();
  if (deployKeys.some((key) => (
    !key
    || typeof key !== "object"
    || Array.isArray(key)
    || !Number.isSafeInteger(key.id)
    || typeof key.read_only !== "boolean"
  ))) {
    fail("deploy key inventory is invalid");
  }
  const writers = deployKeys.filter((key) => key.read_only === false);
  if (writers.length !== 1 || writers[0].id !== deployKeyId) {
    fail("Pages requires exactly one audited write deploy key");
  }
}

function main() {
  const [
    rulesetPath,
    deployKeysPath,
    repository,
    rulesetId,
    rulesetUpdatedAt,
    deployKeyId,
  ] = process.argv.slice(2);
  if (
    !rulesetPath
    || !deployKeysPath
    || !repository
    || !rulesetId
    || !rulesetUpdatedAt
    || !deployKeyId
  ) {
    fail("usage: verify-theme-pages-governance.mjs <ruleset.json> <deploy-keys.json> <repository> <ruleset-id> <ruleset-updated-at> <deploy-key-id>");
  }
  verifyThemePagesGovernance({
    ruleset: readJson(rulesetPath, "ruleset response"),
    deployKeyPages: readJson(deployKeysPath, "deploy key response"),
    repository,
    rulesetId: positiveInteger(rulesetId, "ruleset id"),
    rulesetUpdatedAt,
    deployKeyId: positiveInteger(deployKeyId, "deploy key id"),
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
