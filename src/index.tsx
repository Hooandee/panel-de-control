import {
  PanelSection,
  PanelSectionRow,
  ToggleField,
  Spinner,
  ErrorBoundary,
  staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
// PLACEHOLDER icon — change to one that fits your plugin (and update the <FaPalette/> usage below).
// Browse names: https://react-icons.github.io/react-icons/icons/fa/
import { FaPalette } from "react-icons/fa";
import { useEffect, useState } from "react";

import { getState, setEnabled, PluginState } from "./api";

function Content() {
  // ALL hooks MUST be above any early return, or React throws a minified
  // "invalid hook" error when the panel opens.
  const [state, setState] = useState<PluginState | null>(null);

  useEffect(() => {
    getState().then(setState);
  }, []);

  if (!state) return <Spinner />;

  return (
    <PanelSection title="Panel de Control">
      <PanelSectionRow>
        <ToggleField
          label="Enabled"
          checked={state.enabled}
          onChange={(on) => {
            setState({ ...state, enabled: on }); // optimistic
            setEnabled(on);
          }}
        />
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: "Panel de Control",
  titleView: <div className={staticClasses.Title}>Panel de Control</div>,
  // ErrorBoundary so a render error in our UI can't take down Decky-wide.
  content: (
    <ErrorBoundary>
      <Content />
    </ErrorBoundary>
  ),
  icon: <FaPalette />,
  onDismount() {
    // unregister SteamClient listeners / clear timers here
  },
}));
