export async function readSteamLanguage(): Promise<string | null> {
  try {
    const settings = SteamClient?.Settings as
      | { GetCurrentLanguage?: () => Promise<string> }
      | undefined;
    if (typeof settings?.GetCurrentLanguage !== "function") return null;
    const lang = await settings.GetCurrentLanguage();
    return typeof lang === "string" ? lang : null;
  } catch {
    return null;
  }
}
