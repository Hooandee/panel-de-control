// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { createThemeNavigationAccess } from "./navigationAccess";

interface FakeNode {
  m_element: Element | null;
  m_rgChildren: FakeNode[];
  BTakeFocus: ReturnType<typeof vi.fn<(source?: number) => boolean>>;
}

function node(element: Element | null, children: FakeNode[] = [], takes = true): FakeNode {
  return { m_element: element, m_rgChildren: children, BTakeFocus: vi.fn((_source?: number) => takes) };
}

describe("createThemeNavigationAccess.focus", () => {
  it("uses the host FocusElement when Steam still provides it", () => {
    const element = document.createElement("div");
    const FocusElement = vi.fn();

    const access = createThemeNavigationAccess({ getController: () => ({ FocusElement }) });

    expect(access.focus(element)).toBe(true);
    expect(FocusElement).toHaveBeenCalledWith(element);
  });

  it("moves Steam focus through the element's navigation node when FocusElement is gone", () => {
    const carousel = document.createElement("div");
    const target = node(carousel);
    const root = node(document.body, [node(document.createElement("div"), [target])]);

    const access = createThemeNavigationAccess({
      getController: () => ({ GetActiveNavTree: () => ({ m_Root: root }) }),
    });

    expect(access.focus(carousel)).toBe(true);
    expect(target.BTakeFocus).toHaveBeenCalledOnce();
  });

  it("also searches child navigation trees", () => {
    const element = document.createElement("div");
    const target = node(element);
    const tree = { m_Root: node(document.body), m_rgChildNavTrees: [{ m_Root: node(null, [target]) }] };

    const access = createThemeNavigationAccess({ getController: () => ({ GetActiveNavTree: () => tree }) });

    expect(access.focus(element)).toBe(true);
    expect(target.BTakeFocus).toHaveBeenCalledOnce();
  });

  it("reports failure honestly when no node owns the element or it refuses focus", () => {
    const missing = document.createElement("div");
    const refusing = document.createElement("div");
    const root = node(document.body, [node(refusing, [], false)]);

    const access = createThemeNavigationAccess({
      getController: () => ({ GetActiveNavTree: () => ({ m_Root: root }) }),
    });

    expect(access.focus(missing)).toBe(false);
    expect(access.focus(refusing)).toBe(false);
  });

  it("never throws when the navigation tree is malformed or cyclic", () => {
    const element = document.createElement("div");
    const cyclic = node(document.body);
    cyclic.m_rgChildren.push(cyclic);

    const broken = createThemeNavigationAccess({
      getController: () => ({ GetActiveNavTree: () => { throw new Error("gone"); } }),
    });
    const looping = createThemeNavigationAccess({
      getController: () => ({ GetActiveNavTree: () => ({ m_Root: cyclic }) }),
    });

    expect(broken.focus(element)).toBe(false);
    expect(looping.focus(element)).toBe(false);
  });
});
