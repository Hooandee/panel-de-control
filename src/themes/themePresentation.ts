import hooandeeCover from "../assets/hooandee-cover.jpg";
import type { PublishedThemeRelease } from "./remotePublication";

export function themeCoverFor(release: PublishedThemeRelease): string | undefined {
  return release.catalogId === "hooandee-gallery"
    && release.cssLoaderName === "Hooandee Gallery"
    ? hooandeeCover
    : undefined;
}
