import { openLibrary } from "./StationsModal";

export type BackgroundTab = "collections" | "add" | "games";

export function openBackgroundLibrary(_tab: BackgroundTab = "collections"): void {
  openLibrary("background");
}
