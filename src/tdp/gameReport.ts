export interface GameReport {
  appid: string | null;
  name: string | null;
}

export function isSameGameReport(a: GameReport, b: GameReport): boolean {
  return a.appid === b.appid && a.name === b.name;
}

export function shouldReportGame(
  target: GameReport,
  committed: GameReport,
  inFlight: GameReport | undefined,
): boolean {
  return !isSameGameReport(target, committed)
    && (!inFlight || !isSameGameReport(target, inFlight));
}
