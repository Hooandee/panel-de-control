interface InstallFolder {
  strFolderPath?: string;
  bIsMounted?: boolean;
  vecApps?: readonly { nAppID?: number }[];
}

const globals = globalThis as unknown as { installFolderStore?: { AllInstallFolders?: readonly InstallFolder[] } };

function folders(): readonly InstallFolder[] {
  try {
    // Older clients hand MobX observable arrays, which are not real arrays.
    return Array.from(globals.installFolderStore?.AllInstallFolders ?? []);
  } catch {
    return [];
  }
}

const usable = (folder: InstallFolder): folder is InstallFolder & { strFolderPath: string } =>
  typeof folder?.strFolderPath === "string" && folder.strFolderPath.startsWith("/") && folder.bIsMounted !== false;

/** Every mounted library folder Steam knows: the backend looks there even when libraryfolders.vdf misleads it. */
export function steamLibraryFolders(): string[] {
  return [...new Set(folders().filter(usable).map((folder) => folder.strFolderPath))].slice(0, 32);
}

/** The library folder Steam installed this game in, or null when Steam does not say. */
export function steamLibraryOf(appid: number): string | null {
  const folder = folders().find((item) => usable(item) && Array.from(item.vecApps ?? []).some((app) => app?.nAppID === appid));
  return folder?.strFolderPath ?? null;
}
