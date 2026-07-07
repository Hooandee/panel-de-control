export function shouldSuppress(
  lastSelfWriteMs: number | null,
  nowMs: number,
  windowMs: number,
): boolean {
  if (lastSelfWriteMs === null) return false;
  return nowMs - lastSelfWriteMs < windowMs;
}
