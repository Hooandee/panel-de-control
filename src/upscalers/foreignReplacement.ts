import type { UpscalerJob } from "./types";

export async function replaceForeignInstallation(
  adopt: () => Promise<unknown>,
  install: () => Promise<UpscalerJob>,
  start: (run: () => Promise<UpscalerJob>) => Promise<void>,
  refresh: () => Promise<void>,
): Promise<void> {
  await start(async () => {
    await adopt();
    return install();
  });
  await refresh();
}
