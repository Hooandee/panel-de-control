import { readFlag, writeFlag } from "./pdcStorage";

const KEY = (id: string) => `pdc:collapsed:${id}`;

export function isCollapsed(id: string): boolean {
  return readFlag(KEY(id));
}

export function setCollapsed(id: string, collapsed: boolean): void {
  writeFlag(KEY(id), collapsed);
}
