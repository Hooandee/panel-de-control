import { afterEach, describe, expect, it, vi } from "vitest";

import { createRemotePublicationClient } from "../themes/remotePublicationClient";
import { isMissingBackendMethod, reportStaleBackend, setStaleBackendSink } from "./staleBackend";

// Journal of a Legion Go loading frontend 0.67.1 over a still-loaded 0.37.11 backend.
const JOURNAL_ERRORS = [
  "Plugin object has no attribute list_theme_extensions",
  "Plugin object has no attribute check_theme_releases",
  "Plugin object has no attribute get_theme_activation_recovery",
  "Plugin object has no attribute get_theme_install_recoveries",
];

afterEach(() => setStaleBackendSink(null));

describe("stale backend detection", () => {
  it.each(JOURNAL_ERRORS)("recognises %s", (message) => {
    expect(isMissingBackendMethod(new Error(message))).toBe(true);
  });

  it("recognises the error Decky hands the frontend: empty message, quoted name in the traceback", () => {
    const error = Object.assign(new Error(""), {
      name: "Python Exception",
      pythonTraceback: "Traceback (most recent call last):\n  ...\nAttributeError: 'Plugin' object has no attribute 'check_theme_releases'\n",
    });
    expect(isMissingBackendMethod(error)).toBe(true);
    const sink = vi.fn();
    setStaleBackendSink(sink);
    expect(reportStaleBackend(error)).toBe(true);
    expect(sink).toHaveBeenCalledWith("'Plugin' object has no attribute 'check_theme_releases'");
  });

  it("ignores unrelated failures", () => {
    expect(isMissingBackendMethod(new Error("network down"))).toBe(false);
    expect(isMissingBackendMethod(undefined)).toBe(false);
  });

  it("reports once per session", () => {
    const sink = vi.fn();
    setStaleBackendSink(sink);
    expect(reportStaleBackend(new Error(JOURNAL_ERRORS[0]))).toBe(true);
    expect(reportStaleBackend(new Error(JOURNAL_ERRORS[1]))).toBe(true);
    expect(sink).toHaveBeenCalledTimes(1);
    expect(sink).toHaveBeenCalledWith(JOURNAL_ERRORS[0]);
  });

  it("surfaces the mismatch when the publication check hits a missing RPC", async () => {
    const sink = vi.fn();
    setStaleBackendSink(sink);
    const result = await createRemotePublicationClient(async () => {
      throw new Error(JOURNAL_ERRORS[1]);
    }).check(false);

    expect(result).toEqual({ status: "recoverable-failure", code: "invalid_descriptor", retryable: true });
    expect(sink).toHaveBeenCalledWith(JOURNAL_ERRORS[1]);
  });

  it("stays silent for ordinary publication failures", async () => {
    const sink = vi.fn();
    setStaleBackendSink(sink);
    await createRemotePublicationClient(async () => {
      throw new Error("timeout");
    }).check(false);

    expect(sink).not.toHaveBeenCalled();
  });
});
