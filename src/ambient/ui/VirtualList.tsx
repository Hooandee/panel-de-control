import { Focusable, type GamepadEvent } from "@decky/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { nearEnd, visibleRange } from "../core/virtualWindow";

interface Props<T> {
  items: readonly T[];
  rowHeight: number;
  height: number;
  renderRow: (item: T, index: number) => ReactNode;
  keyOf: (item: T) => string;
  controllerNavigation?: boolean;
  onEndReached?: () => void;
}

/** Fixed-height rows; only the visible window is in the DOM so long station lists stay light. */
export function VirtualList<T>({ items, rowHeight, height, renderRow, keyOf, onEndReached, controllerNavigation = false }: Props<T>) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const range = visibleRange(scrollTop, height, rowHeight, items.length);

  useEffect(() => {
    if (onEndReached && nearEnd(range, items.length)) onEndReached();
  }, [range.end, items.length]);

  useEffect(() => {
    if (ref.current && items.length === 0) ref.current.scrollTop = 0;
  }, [items.length]);

  const Container = controllerNavigation ? Focusable : "div";
  const onGamepadFocus = (event: GamepadEvent) => {
    const row = (event.target as HTMLElement)?.closest?.<HTMLElement>("[data-virtual-row]");
    const container = ref.current;
    if (!row || !container) return;
    const top = Number(row.dataset.virtualRow) * rowHeight;
    const next = top < container.scrollTop ? top : top + rowHeight > container.scrollTop + height ? top + rowHeight - height : container.scrollTop;
    if (next !== container.scrollTop) {
      container.scrollTop = next;
      setScrollTop(next);
    }
  };

  return (
    <Container {...(controllerNavigation ? { "flow-children": "column", onGamepadFocus } : {})} ref={ref} onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)} style={{ height, overflowY: "auto", position: "relative" }}>
      <div style={{ height: items.length * rowHeight, position: "relative" }}>
        {items.slice(range.start, range.end).map((item, offset) => {
          const index = range.start + offset;
          return (
            <div key={keyOf(item)} data-virtual-row={index} style={{ position: "absolute", top: index * rowHeight, left: 0, right: 0, height: rowHeight }}>
              {renderRow(item, index)}
            </div>
          );
        })}
      </div>
    </Container>
  );
}
