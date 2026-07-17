import { callBackend, disabledPlugins, installedPlugins } from "../deckyInternal";

export { disabledPlugins, installedPlugins };

/**
 * Disable a plugin via the same loader RPC the Decky UI uses (reversible from
 * Decky). Only reports success once the plugin actually shows up in
 * `disabledPlugins()`. The state may take a tick to update, so a caller that
 * re-reads shortly after will still see the truth.
 */
export async function disablePlugin(name: string): Promise<boolean> {
  try {
    await callBackend("utilities/disable_plugin", name);
    return disabledPlugins().includes(name);
  } catch {
    return false;
  }
}
