export function readFlag(key: string, fallback = false): boolean {
  try {
    const v = window.localStorage?.getItem(key);
    return v === null || v === undefined ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

export function writeFlag(key: string, on: boolean): void {
  try {
    window.localStorage?.setItem(key, on ? "1" : "0");
  } catch {}
}
