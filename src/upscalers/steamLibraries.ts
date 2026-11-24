interface InstallFolder {
  strFolderPath?: string;
  bIsMounted?: boolean;
}

const globals = globalThis as unknown as { installFolderStore?: { AllInstallFolders?: readonly InstallFolder[] } };

function folders(): readonly InstallFolder[] {
  try {
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
