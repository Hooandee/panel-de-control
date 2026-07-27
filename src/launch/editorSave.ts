export interface SaveState {
  loaded: boolean;
  malformed: boolean;
  dirty: boolean;
  preview: string;
}

/** The string to persist for the current edit, or null when nothing needs saving. */
export function pendingSave({ loaded, malformed, dirty, preview }: SaveState): string | null {
  if (!loaded || malformed || !dirty) return null;
  return preview;
}
