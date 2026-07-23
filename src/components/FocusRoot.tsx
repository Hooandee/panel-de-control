import { CSSProperties, FC, ReactNode, useCallback } from "react";
import { ensureFocusStyles, PDC_ROOT } from "../focus";
import { currentAccentRgb } from "../system/accentColor";
import { useAccent } from "../system/useAccent";
import { setQamDocument } from "../qamDocument";

interface Props {
  children: ReactNode;
  style?: CSSProperties;
  // The main panel root publishes its document so the plugin-list localizer can
  // reach the surrounding QAM. Modals are separate documents — they must not set it.
  publishDocument?: boolean;
}

// Scopes the focus ring to its subtree and injects the sheet into that subtree's own
// document — the panel and each showModal modal are separate documents, and the
// plugin's `document` global is neither.
export const FocusRoot: FC<Props> = ({ children, style, publishDocument }) => {
  useAccent(); // recolour when the accent changes
  const ref = useCallback(
    (el: HTMLDivElement | null) => {
      if (!el) return;
      ensureFocusStyles(el.ownerDocument);
      if (publishDocument) setQamDocument(el.ownerDocument);
    },
    [publishDocument],
  );
  const vars = { [`--pdc-accent-rgb`]: currentAccentRgb() } as CSSProperties;
  return (
    <div className={PDC_ROOT} ref={ref} style={{ ...vars, ...style }}>
      {children}
    </div>
  );
};
