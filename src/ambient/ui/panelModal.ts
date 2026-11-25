import { Navigation, QuickAccessTab } from "@decky/ui";

/** The libraries open over Home with the QAM closed, so the themed glass shows the user's background. */
export function leavePanel(): void {
  try {
    Navigation.CloseSideMenus();
  } catch {
    /* navigation unavailable; the modal still opens */
  }
}

/** Closing a library goes back to Ambiente in the QAM instead of to the game or Home. */
export function backToPanel(closeModal?: () => void): () => void {
  return () => {
    closeModal?.();
    try {
      Navigation.OpenQuickAccessMenu(QuickAccessTab.Decky);
    } catch {
      /* navigation unavailable */
    }
  };
}
