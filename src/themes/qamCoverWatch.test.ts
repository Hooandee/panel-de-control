// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../system/uiActivity", () => ({ findQamNavigationDocument: () => null }));

import { qamCovered, watchQamCover } from "./qamCoverWatch";

function documentWithStyle(): Document {
  document.body.style.filter = "";
  return document;
}

describe("QAM cover watch", () => {
  afterEach(() => { vi.useRealTimers(); document.head.innerHTML = ""; document.body.style.filter = ""; });

  it("only treats a filter on the root as covering", () => {
    expect(qamCovered(documentWithStyle())).toBe(false);
    document.body.style.filter = "hue-rotate(120deg)";
    expect(qamCovered(document)).toBe(true);
  });

  it("warns once when a style covers the menu and again only after it recovers", async () => {
    vi.useFakeTimers();
    const target = documentWithStyle();
    const onCovered = vi.fn();
    const stop = watchQamCover(onCovered, () => target);

    target.body.style.filter = "invert(1)";
    target.head.append(target.createElement("style"));
    await vi.advanceTimersByTimeAsync(600);
    target.head.append(target.createElement("style"));
    await vi.advanceTimersByTimeAsync(600);
    expect(onCovered).toHaveBeenCalledTimes(1);

    target.body.style.filter = "";
    target.head.append(target.createElement("style"));
    await vi.advanceTimersByTimeAsync(600);
    target.body.style.filter = "invert(1)";
    target.head.append(target.createElement("style"));
    await vi.advanceTimersByTimeAsync(600);
    expect(onCovered).toHaveBeenCalledTimes(2);
    stop();
  });

  it("gives up looking for the menu after a few bounded retries", async () => {
    vi.useFakeTimers();
    const find = vi.fn(() => null);
    const stop = watchQamCover(vi.fn(), find);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(find).toHaveBeenCalledTimes(4);
    stop();
  });
});
