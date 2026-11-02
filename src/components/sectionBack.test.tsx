// @vitest-environment happy-dom
import { cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SectionBackContext, useSectionBack } from "./sectionBack";

afterEach(cleanup);

describe("useSectionBack", () => {
  it("lends the override to the shell and returns it on unmount", () => {
    const set = vi.fn();
    const onBack = vi.fn();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SectionBackContext.Provider value={{ shown: true, set }}>{children}</SectionBackContext.Provider>
    );
    const { result, unmount } = renderHook(() => useSectionBack({ label: "Juegos", onBack }), { wrapper });
    expect(result.current).toBe(true);
    expect(set).toHaveBeenLastCalledWith({ label: "Juegos", onBack });
    unmount();
    expect(set).toHaveBeenLastCalledWith(null);
  });

  it("asks the view to draw its own back outside the shell header", () => {
    const { result } = renderHook(() => useSectionBack({ label: "Juegos", onBack: () => undefined }));
    expect(result.current).toBe(false);
  });
});
