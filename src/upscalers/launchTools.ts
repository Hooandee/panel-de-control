import { parse } from "../launch/compose";

function unquote(value: string): string { return value.replace(/^(["'])(.*)\1$/, "$2"); }

export function configuredLaunchTools(launch: string): string[] {
  const parsed = parse(launch);
  if (parsed.malformed) return [];
  const names = new Set<string>();
  for (const token of parsed.wrappers) {
    const name = unquote(token).split("/").pop() ?? "";
    if (["mako-run", "mako-launch", "mako-framegen"].includes(name)) names.add("Mako");
    if (["lsfg", "lsfg-vk", "lsfg-run"].includes(name)) names.add("Lossless Scaling");
  }
  for (const { name, value } of parsed.envs) {
    if (!unquote(value) || unquote(value) === "0") continue;
    if (["LSFGVK_PROFILE", "LSFG_PROCESS"].includes(name)) names.add("Lossless Scaling");
    if (["MAKO_CONFIG", "MAKO_PROFILE"].includes(name)) names.add("Mako");
    if (name === "WINE_FULLSCREEN_FSR") names.add("FSR");
    if (name === "PROTON_FSR4_UPGRADE") names.add("Proton FSR 4");
  }
  return [...names];
}
