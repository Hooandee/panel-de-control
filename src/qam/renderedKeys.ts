export function readRenderedQamKeys(document: Document | null): string[] | null {
  // Steam retains the previous QAM DOM while a fullscreen editor is open.
  if (!document || document.hidden) return null;
  return Array.from(
    document.querySelectorAll<HTMLElement>("[id^='quickaccess_tab_']"),
    (entry) => entry.id.slice("quickaccess_tab_".length),
  );
}
