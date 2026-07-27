import { callBackend, disabledPlugins, installedPlugins } from "../deckyInternal";

export { disabledPlugins, installedPlugins };

// Disable a plugin via the loader RPC (reversible from Decky). Reports success only
// once it actually shows up in disabledPlugins() — the state may take a tick.
export async function disablePlugin(name: string): Promise<boolean> {
  try {
    await callBackend("utilities/disable_plugin", name);
    return disabledPlugins().includes(name);
  } catch {
    return false;
  }
}
