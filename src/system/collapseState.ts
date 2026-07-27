import { readFlag, writeFlag } from "./pdcStorage";

const KEY = (id: string) => `pdc:collapsed:${id}`;

export function isCollapsed(id: string, fallback = false): boolean {
  return readFlag(KEY(id), fallback);
}

export function setCollapsed(id: string, collapsed: boolean): void {
  writeFlag(KEY(id), collapsed);
}
