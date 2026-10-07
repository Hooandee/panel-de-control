import { CSSProperties, FC, ReactNode, useCallback, useEffect, useState } from "react";
import { ensureFocusStyles, PDC_ROOT } from "../focus";
import { currentAccentRgb } from "../system/accentColor";
import { useAccent } from "../system/useAccent";
import { setQamDocument } from "../qamDocument";
import { watchThemeAccent } from "../system/themeAccent";

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
  const [panelDocument, setPanelDocument] = useState<Document | null>(null);
  const ref = useCallback(
    (el: HTMLDivElement | null) => {
      if (!el) return;
      ensureFocusStyles(el.ownerDocument);
      if (publishDocument) {
        setQamDocument(el.ownerDocument);
        setPanelDocument(el.ownerDocument);
      }
    },
    [publishDocument],
  );
  useEffect(() => (panelDocument ? watchThemeAccent(panelDocument) : undefined), [panelDocument]);
  const vars = { [`--pdc-accent-rgb`]: currentAccentRgb() } as CSSProperties;
  return (
    <div className={PDC_ROOT} ref={ref} style={{ ...vars, ...style }}>
      {children}
    </div>
  );
};
