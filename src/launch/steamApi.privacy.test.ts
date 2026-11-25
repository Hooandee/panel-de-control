// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { setUiEventSink } from "../system/uiEvents";
import { writeLaunchOptions } from "./steamApi";

describe("private launch writes", () => {
  afterEach(() => {
    setUiEventSink(null);
    delete (window as unknown as { SteamClient?: unknown }).SteamClient;
  });

  it("writes private parameters but excludes them and thrown messages from the journal", () => {
    const journal: string[] = [];
    const secret = 'MAKO_CONFIG="/home/private-owner/config.json" %command%';
    let written = "";
    (window as unknown as { SteamClient: unknown }).SteamClient = { Apps: { SetAppLaunchOptions: (_id: number, value: string) => { written = value; } } };
    setUiEventSink((_area, _action, detail) => { journal.push(detail); });
    expect(writeLaunchOptions(1, secret, false, true)).toBe(true);
    expect(written).toBe(secret);
    setUiEventSink(null);
    expect(journal.join("")).not.toContain("private-owner");
    expect(journal.join("")).toContain('"redacted":true');
    (window as unknown as { SteamClient: unknown }).SteamClient = { Apps: { SetAppLaunchOptions: () => { throw new Error(secret); } } };
    setUiEventSink((_area, _action, detail) => { journal.push(detail); });
    expect(writeLaunchOptions(1, secret, false, true)).toBe(false);
    setUiEventSink(null);
    expect(journal.join("")).not.toContain("private-owner");
    expect(journal.join("")).toContain("setter_failed");
  });
});
