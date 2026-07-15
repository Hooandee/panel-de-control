import { CSSProperties, FC, ReactNode, useCallback } from "react";
import { ensureFocusStyles, PDC_ROOT } from "../focus";
import { currentAccentRgb } from "../system/accentColor";
import { useAccent } from "../system/useAccent";

interface Props {
  children: ReactNode;
  style?: CSSProperties;
}

// Scopes the focus ring to its subtree and injects the sheet into that subtree's own
// document — the panel and each showModal modal are separate documents, and the
// plugin's `document` global is neither.
export const FocusRoot: FC<Props> = ({ children, style }) => {
  useAccent(); // recolour when the accent changes
  const ref = useCallback((el: HTMLDivElement | null) => {
    if (el) ensureFocusStyles(el.ownerDocument);
  }, []);
  const vars = { [`--pdc-accent-rgb`]: currentAccentRgb() } as CSSProperties;
  return (
    <div className={PDC_ROOT} ref={ref} style={{ ...vars, ...style }}>
      {children}
    </div>
  );
};
