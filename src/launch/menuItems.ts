export function replaceMenuItem<T extends { key?: unknown }>(
  items: unknown,
  key: string,
  item: T,
  before: (candidate: T) => boolean,
): boolean {
  if (!Array.isArray(items)) return false;
  const menu = items as T[];
  for (let i = menu.length - 1; i >= 0; i -= 1) {
    if (menu[i]?.key === key) menu.splice(i, 1);
  }
  const index = menu.findIndex(before);
  if (index >= 0) menu.splice(index, 0, item);
  else menu.push(item);
  return true;
}
