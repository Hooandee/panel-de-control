export interface WindowRange {
  start: number;
  end: number;
}

/** Rows to render for a fixed-height list: the visible ones plus an overscan on both sides. */
export function visibleRange(scrollTop: number, viewport: number, rowHeight: number, count: number, overscan = 6): WindowRange {
  if (count <= 0 || rowHeight <= 0) return { start: 0, end: 0 };
  const first = Math.floor(Math.max(0, scrollTop) / rowHeight);
  const visible = Math.ceil(Math.max(0, viewport) / rowHeight) + 1;
  return { start: Math.max(0, first - overscan), end: Math.min(count, first + visible + overscan) };
}

/** True once the window gets close enough to the end that the next page should load. */
export function nearEnd(range: WindowRange, count: number, threshold = 8): boolean {
  return count > 0 && range.end >= count - threshold;
}
