const COUNTRY = /^[A-Z]{2}$/;

/**
 * The listener's country for "Near you": Steam's own IP country first (it knows where the
 * connection is), then the language region. The system timezone is not used: handhelds often
 * keep a wrong one.
 */
export async function homeCountry(language: string = typeof navigator !== "undefined" ? navigator.language : ""): Promise<string | null> {
  try {
    const user = (globalThis as unknown as { SteamClient?: { User?: { GetIPCountry?: () => Promise<string> | string } } }).SteamClient?.User;
    const ip = String((await user?.GetIPCountry?.()) ?? "").trim().toUpperCase();
    if (COUNTRY.test(ip)) return ip;
  } catch {
    /* Steam API unavailable: fall back to the language region */
  }
  const region = /-([A-Za-z]{2})$/.exec(language)?.[1]?.toUpperCase() ?? "";
  return COUNTRY.test(region) ? region : null;
}
