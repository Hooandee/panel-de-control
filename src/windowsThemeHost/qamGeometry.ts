// Steam on Windows opens quick access as a window narrower and shorter than on the Deck (Ally X at 1080p: the right
// 348 of 1353 CSS px, 40 px below the top and 41 above the bottom). Themes that frame it read these properties.
export const QAM_GEOMETRY_PROPERTIES = {
  width: "--pdc-host-qam-width",
  top: "--pdc-host-qam-top",
  bottom: "--pdc-host-qam-bottom",
} as const;

export interface QamGeometry {
  width: number;
  top: number;
  bottom: number;
}

type WindowFrame = Pick<Window, "screenX" | "screenY" | "innerWidth" | "innerHeight" | "devicePixelRatio">;

/** The visible quick access panel in Big Picture's CSS pixels, or null while it is not on screen. */
export function measureQamGeometry(qam: WindowFrame, steam: WindowFrame): QamGeometry | null {
  if (qam.innerWidth <= 0 || qam.innerHeight <= 0 || steam.innerWidth <= 0 || steam.innerHeight <= 0) return null;
  const scale = qam.devicePixelRatio / steam.devicePixelRatio;
  const left = (qam.screenX - steam.screenX) * scale;
  const top = (qam.screenY - steam.screenY) * scale;
  const right = Math.min(left + qam.innerWidth * scale, steam.innerWidth);
  const bottom = top + qam.innerHeight * scale;
  if (left < 0 || left >= steam.innerWidth || right <= left) return null;
  const clamp = (value: number, max: number) => Math.round(Math.min(Math.max(value, 0), max));
  return {
    width: clamp(right - left, steam.innerWidth),
    top: clamp(top, steam.innerHeight),
    bottom: clamp(steam.innerHeight - bottom, steam.innerHeight),
  };
}

export function applyQamGeometry(doc: Document, geometry: QamGeometry | null): void {
  const style = doc.documentElement.style;
  for (const key of Object.keys(QAM_GEOMETRY_PROPERTIES) as (keyof QamGeometry)[]) {
    const property = QAM_GEOMETRY_PROPERTIES[key];
    if (geometry) {
      const value = `${geometry[key]}px`;
      if (style.getPropertyValue(property) !== value) style.setProperty(property, value);
    } else {
      style.removeProperty(property);
    }
  }
}
