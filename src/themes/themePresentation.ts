import hooandeeCover from "../assets/hooandee-cover.jpg";
import luminousAtlasCover from "../assets/luminous-atlas-cover.jpg";
import type { PublishedThemeRelease } from "./remotePublication";

const COVERS: Readonly<Record<string, { cssLoaderName: string; cover: string }>> = {
  "hooandee-gallery": { cssLoaderName: "Hooandee Gallery", cover: hooandeeCover },
  "hooandee-luminous-atlas": { cssLoaderName: "Hooandee Luminous Atlas", cover: luminousAtlasCover },
};

export function themeCoverFor(release: PublishedThemeRelease): string | undefined {
  const entry = Object.prototype.hasOwnProperty.call(COVERS, release.catalogId) ? COVERS[release.catalogId] : undefined;
  return entry?.cssLoaderName === release.cssLoaderName ? entry.cover : undefined;
}
