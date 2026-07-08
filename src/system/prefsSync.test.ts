import { describe, it, expect } from "vitest";
import { isDurableKey, planPrefsSync } from "./prefsSync";

describe("isDurableKey", () => {
  it("mirrors the language key and the pdc: namespace", () => {
    expect(isDurableKey("panel-de-control-lang")).toBe(true);
    expect(isDurableKey("pdc:layout")).toBe(true);
    expect(isDurableKey("pdc:collapsed:battery")).toBe(true);
    expect(isDurableKey("pdc:valueToast:enabled")).toBe(true);
  });
  it("excludes the ephemeral active-tab and unmanaged keys", () => {
    expect(isDurableKey("pdc:activeTab")).toBe(false);
    expect(isDurableKey("some-other-key")).toBe(false);
  });
});

describe("planPrefsSync", () => {
  it("heals from the backend (backend wins)", () => {
    const { heal, migrate } = planPrefsSync(
      { "panel-de-control-lang": "en" },
      { "panel-de-control-lang": "es" },
    );
    expect(heal).toEqual({ "panel-de-control-lang": "en" });
    expect(migrate).toEqual({});
  });
  it("migrates a durable local-only key up to the backend", () => {
    const { heal, migrate } = planPrefsSync({}, { "pdc:layout": "{}" });
    expect(heal).toEqual({});
    expect(migrate).toEqual({ "pdc:layout": "{}" });
  });
  it("never migrates or heals ephemeral keys", () => {
    const { heal, migrate } = planPrefsSync(
      { "pdc:activeTab": "nav.system" },
      { "pdc:activeTab": "nav.power" },
    );
    expect(heal).toEqual({});
    expect(migrate).toEqual({});
  });
  it("combines heal and migrate across keys", () => {
    const { heal, migrate } = planPrefsSync(
      { "panel-de-control-lang": "en" },
      { "panel-de-control-lang": "es", "pdc:valueToast:enabled": "1" },
    );
    expect(heal).toEqual({ "panel-de-control-lang": "en" });
    expect(migrate).toEqual({ "pdc:valueToast:enabled": "1" });
  });
});
