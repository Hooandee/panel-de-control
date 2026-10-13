import { Focusable } from "@decky/ui";
import { type ComponentProps, type FC, useRef } from "react";

import { useRefocusWhenRemoved } from "./refocusWhenRemoved";

// A row of controls that one of its own buttons can delete.
export const RemovableRow: FC<Omit<ComponentProps<typeof Focusable>, "ref" | "flow-children">> = (props) => {
  const ref = useRef<HTMLDivElement>(null);
  useRefocusWhenRemoved(ref);
  return <Focusable ref={ref} flow-children="row" {...props} />;
};
