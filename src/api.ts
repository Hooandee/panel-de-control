import { callable } from "@decky/api";

// callable<[arg types], ReturnType>("exact_backend_method_name")
// Names must match the Python `async def` on the Plugin class exactly.
export const getVersion = callable<[], string>("get_version");
export const getState = callable<[], PluginState>("get_state");
export const setEnabled = callable<[on: boolean], void>("set_enabled");

export interface PluginState {
  enabled: boolean;
}
