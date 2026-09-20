// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getLearningStatus: vi.fn(),
}));

vi.mock("../api", () => ({
  getLearningStatus: mocks.getLearningStatus,
}));

import { notifyLearningStatusChanged } from "./statusInvalidation";
import { useLearningStatus } from "./useLearningStatus";

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useLearningStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("refreshes AutoTDP ownership without requiring a game change", async () => {
    let autoTdpActive = false;
    mocks.getLearningStatus.mockImplementation(async () => ({
      telemetry_enabled: true,
      tdp_supported: true,
      fan_supported: true,
      auto_tdp_active: autoTdpActive,
    }));

    const { result, unmount } = renderHook(() => useLearningStatus("42"));
    await settle();
    expect(result.current.status?.auto_tdp_active).toBe(false);

    autoTdpActive = true;
    act(() => notifyLearningStatusChanged());
    await settle();

    expect(result.current.status?.auto_tdp_active).toBe(true);
    expect(mocks.getLearningStatus).toHaveBeenCalledTimes(2);
    unmount();
  });
});
