import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";


const reusable = readFileSync(resolve(".github/workflows/_theme-package.yml"), "utf8");
const gallery = readFileSync(resolve(".github/workflows/theme-gallery.yml"), "utf8");
const prerelease = readFileSync(resolve(".github/workflows/prerelease.yml"), "utf8");
const release = readFileSync(resolve(".github/workflows/release-please.yml"), "utf8");
const deploy = readFileSync(resolve("scripts/deploy-to-device.sh"), "utf8");

function workflow(path: string): string {
  return existsSync(resolve(path)) ? readFileSync(resolve(path), "utf8") : "";
}

const reusableStage = workflow(".github/workflows/_theme-stage.yml");
const reusablePromote = workflow(".github/workflows/_theme-promote.yml");
const galleryStage = workflow(".github/workflows/theme-gallery-stage.yml");
const galleryPromote = workflow(".github/workflows/theme-gallery-promote.yml");

describe("Gallery distribution workflow", () => {
  it("is a read-only pinned artifact pipeline with immutable versions", () => {
    expect(reusable).toContain("workflow_call:");
    expect(reusable).toContain("contents: read");
    expect(reusable).not.toMatch(/^\s+[a-z-]+: write$/m);
    expect(reusable).toContain("persist-credentials: false");
    expect(reusable).toContain("fetch-depth: 0");
    expect(reusable).toContain("scripts/check-theme-version.mjs");
    for (const action of ["actions/checkout", "pnpm/action-setup", "actions/setup-node", "actions/upload-artifact"]) {
      expect(reusable).toMatch(new RegExp(`${action}@[0-9a-f]{40}`));
    }
    expect(reusable).toContain("if-no-files-found: error");
    expect(reusable).not.toMatch(/^\s*(?:release|tags):/m);
  });

  it("routes Gallery changes to its reusable package contract", () => {
    expect(gallery).toContain("uses: ./.github/workflows/_theme-package.yml");
    expect(gallery).toContain("theme_id: gallery");
    expect(gallery).toContain("theme_directory: themes/gallery");
    expect(gallery).toContain("contract_test: tests/galleryPackage.test.ts");
    expect(gallery).toContain("base_ref:");
    expect(gallery).toContain('"themes/gallery/**"');
    expect(gallery).toContain('"scripts/check-theme-version.mjs"');
    for (const publicationPath of [
      '"scripts/build-theme-publication.mjs"',
      '"scripts/resolve-theme-panel-minimum.mjs"',
      '"scripts/promote-theme-pages.mjs"',
      '"scripts/stage-theme-pages.mjs"',
      '"scripts/theme-publication-contract.mjs"',
      '"scripts/verify-theme-pages.mjs"',
      '".github/workflows/_theme-stage.yml"',
      '".github/workflows/_theme-promote.yml"',
      '"tests/themePagesStage.test.ts"',
      '"tests/themePagesPromote.test.ts"',
      '"tests/themePagesVerify.test.ts"',
      '"tests/themePanelMinimum.test.ts"',
    ]) {
      expect(gallery).toContain(publicationPath);
    }
    expect(reusable).toContain("tests/themePublicationContract.test.ts");
    expect(reusable).toContain("tests/themePagesStage.test.ts");
    expect(reusable).toContain("tests/themePagesPromote.test.ts");
    expect(reusable).toContain("tests/themePagesVerify.test.ts");
    expect(gallery).not.toContain('"src/index.tsx"');
  });

  it("packages the plugin from the immutable bundled pin instead of the live theme source", () => {
    for (const consumer of [prerelease, release, deploy]) {
      expect(consumer).toContain(
        "scripts/copy-bundled-theme.mjs themes/bundled/hooandee-gallery/0.7.8",
      );
      expect(consumer).not.toContain(
        "scripts/package-theme.mjs themes/gallery",
      );
    }
  });

  it("keeps staging and promotion as separate protected manual operations", () => {
    expect(galleryStage).toContain("workflow_dispatch:");
    expect(galleryStage).toContain("uses: ./.github/workflows/_theme-stage.yml");
    expect(galleryStage).toContain("confirmation:");
    expect(galleryStage).toContain("version:");
    expect(galleryStage).not.toMatch(/^\s+(?:push|pull_request|release):/m);

    expect(galleryPromote).toContain("workflow_dispatch:");
    expect(galleryPromote).toContain("uses: ./.github/workflows/_theme-promote.yml");
    expect(galleryPromote).toContain("confirmation:");
    expect(galleryPromote).toContain("version:");
    expect(galleryPromote).not.toMatch(/^\s+(?:push|pull_request|release):/m);
  });

  it("stages only immutable bytes and promotes only the reviewed descriptor", () => {
    expect(reusableStage).toContain("scripts/build-theme-publication.mjs");
    expect(reusableStage).toContain("scripts/resolve-theme-panel-minimum.mjs");
    expect(reusableStage).toContain("tests/themePanelMinimum.test.ts");
    expect(reusableStage).not.toContain("require('./package.json').version");
    expect(reusableStage).not.toContain(" 0.31.4 2.1.2 9");
    expect(reusableStage).toContain("scripts/stage-theme-pages.mjs");
    expect(reusableStage).toContain("scripts/verify-theme-pages.mjs");
    expect(reusableStage).toContain(" immutable");
    expect(reusableStage).not.toContain("scripts/promote-theme-pages.mjs");
    expect(reusableStage).toContain("environment: theme-pages-stage");
    expect(reusableStage).toContain("ref: gh-pages");
    expect(reusableStage).toContain("git/matching-refs/heads/gh-pages");
    expect(reusableStage).toContain("rulesets/$RULESET_ID");
    expect(reusableStage).toContain("theme-pages-immutable");
    expect(reusableStage).toContain("THEME_PAGES_RULESET_ID");
    expect(reusableStage).toContain("THEME_PAGES_RULESET_UPDATED_AT");
    expect(reusableStage).toContain(".updated_at == $updated");
    expect(reusableStage).toContain('index("creation")');
    expect(reusableStage).toContain('index("update")');
    expect(reusableStage).toContain('index("deletion")');
    expect(reusableStage).toContain('index("non_fast_forward")');
    expect(reusableStage).toContain("THEME_PAGES_DEPLOY_KEY");
    expect(reusableStage).toContain("ssh-key:");
    expect(reusableStage.indexOf("ssh-key:")).toBeGreaterThan(reusableStage.indexOf("pnpm install"));
    expect(reusableStage).toContain("git checkout --orphan gh-pages");
    expect(reusableStage).toContain("steps.pages-branch.outputs.exists");
    expect(reusableStage).toContain("theme-pages-publication");

    expect(reusablePromote).toContain("scripts/promote-theme-pages.mjs");
    expect(reusablePromote).toContain("scripts/verify-theme-pages.mjs");
    expect(reusablePromote).toContain(" latest");
    expect(reusablePromote).not.toContain("scripts/build-theme-publication.mjs");
    expect(reusablePromote).not.toContain("scripts/stage-theme-pages.mjs");
    expect(reusablePromote).toContain("environment: theme-pages-promote");
    expect(reusablePromote).toContain("ref: gh-pages");
    expect(reusablePromote).toContain("rulesets/$RULESET_ID");
    expect(reusablePromote).toContain("theme-pages-immutable");
    expect(reusablePromote).toContain("THEME_PAGES_RULESET_ID");
    expect(reusablePromote).toContain("THEME_PAGES_RULESET_UPDATED_AT");
    expect(reusablePromote).toContain(".updated_at == $updated");
    expect(reusablePromote).toContain('index("creation")');
    expect(reusablePromote).toContain('index("update")');
    expect(reusablePromote).toContain('index("deletion")');
    expect(reusablePromote).toContain('index("non_fast_forward")');
    expect(reusablePromote).toContain("THEME_PAGES_DEPLOY_KEY");
    expect(reusablePromote).toContain("ssh-key:");
    expect(reusablePromote.indexOf("ssh-key:")).toBeGreaterThan(reusablePromote.indexOf("pnpm install"));
    const liveVerification = reusablePromote.indexOf("Verify the live immutable candidate before promotion");
    const pointerMutation = reusablePromote.indexOf("Promote the exact immutable descriptor");
    expect(liveVerification).toBeGreaterThan(0);
    expect(pointerMutation).toBeGreaterThan(liveVerification);
    expect(reusablePromote).toContain('"../pages-tree/themes/v1/${{ inputs.catalog_id }}/$VERSION"');
    expect(reusablePromote).toContain("theme-pages-publication");
  });

  it("pins every Pages action and grants write permissions only to publication jobs", () => {
    const publication = [reusableStage, reusablePromote, galleryStage, galleryPromote].join("\n");
    for (const action of [
      "actions/checkout",
      "pnpm/action-setup",
      "actions/setup-node",
      "actions/configure-pages",
      "actions/upload-pages-artifact",
      "actions/deploy-pages",
    ]) {
      const references = publication.match(new RegExp(`${action}@[0-9a-f]{40}`, "g")) ?? [];
      expect(references.length).toBeGreaterThan(0);
    }
    expect(publication).toContain("contents: read");
    expect(publication).not.toContain("contents: write");
    expect(publication).toContain("pages: write");
    expect(publication).toContain("id-token: write");
    expect(publication).toContain("actions: read");
    expect(reusableStage).toContain("github.repository == 'Hooandee/panel-de-control'");
    expect(reusablePromote).toContain("github.repository == 'Hooandee/panel-de-control'");
    expect(reusableStage).toContain("github.event.repository.default_branch");
    expect(reusablePromote).toContain("github.event.repository.default_branch");
  });
});
