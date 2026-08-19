import { describe, expect, it } from "vitest";

import { releaseNotesForLanguage } from "./releaseNotes";

describe("releaseNotesForLanguage", () => {
  it("filters each release independently when translations use a different order", () => {
    const notes = [
      "## v0.37.1",
      "### Novità",
      "- Prima modifica",
      "### What's new",
      "- First change",
      "## v0.37.0",
      "### What's new",
      "- Previous change",
      "### Novità",
      "- Modifica precedente",
    ].join("\n");

    expect(releaseNotesForLanguage(notes, "it")).toBe([
      "## v0.37.1",
      "- Prima modifica",
      "",
      "## v0.37.0",
      "- Modifica precedente",
    ].join("\n"));
  });

  it("falls back to English when the selected translation is missing", () => {
    const notes = [
      "## v0.36.0",
      "### Novedades",
      "- Cambio en español",
      "### What's new",
      "- English change",
    ].join("\r\n");

    expect(releaseNotesForLanguage(notes, "it")).toBe(
      "## v0.36.0\n- English change",
    );
  });

  it("stops at the next heading even when its language is unknown", () => {
    const notes = [
      "## v0.36.0",
      "### What's new",
      "- English change",
      "### Français",
      "- Changement français",
    ].join("\n");

    expect(releaseNotesForLanguage(notes, "en")).toBe(
      "## v0.36.0\n- English change",
    );
  });
});
