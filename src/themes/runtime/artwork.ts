export function safeArtworkUrl(value: string): string | null {
  const trimmed = value.trim();
  if (/^data:image\/[a-z0-9.+-]+(?:;[^,]*)?,/i.test(trimmed)) return trimmed;
  try {
    const url = new URL(trimmed);
    return ["https:", "http:", "blob:"].includes(url.protocol) ? trimmed : null;
  } catch {
    return null;
  }
}
