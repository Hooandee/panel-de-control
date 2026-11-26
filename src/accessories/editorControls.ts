import { createContext, useContext } from "react";

export interface EditorControls {
  /** Closes at once: after saving or showing on the panel. */
  close: () => void;
  /** Back / B: asks first when there are unsaved changes. */
  leave: () => void;
  markDirty: () => void;
}

export const EditorContext = createContext<EditorControls>({ close: () => {}, leave: () => {}, markDirty: () => {} });
export const useEditorControls = () => useContext(EditorContext);
