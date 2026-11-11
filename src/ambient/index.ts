import { registerGlobal } from "../platform/globalComponent";

import { registerCatalog } from "../i18n";
import type { GameSessionPort } from "../platform/gameSessions";
import type { PowerPort } from "../platform/power";
import { getAmbientThemeImages, keepAmbientThemeImages, registerAmbientThemeImage } from "./steam/rpc";
import { AmbientRuntime } from "./steam/runtime";
import { AmbientThemeChannel } from "./steam/themeChannel";
import { ThemeImages } from "./steam/themeImages";
import { FloatingPlayer } from "./ui/FloatingPlayer";
import { QamSidePlayer } from "./ui/QamSidePlayer";
import { openThemeImagePicker } from "./ui/ThemeImagePicker";
import { AMBIENT_STRINGS } from "./ui/strings";
import { setAmbientRuntime } from "./ui/useAmbient";

export { AmbienteSection, AmbientPlayerBlock } from "./ui/AmbienteSection";

registerCatalog(AMBIENT_STRINGS);

/** Handed to the theme runtime host so theme runtimes can claim and host the background. */
export const ambientThemeChannel = new AmbientThemeChannel();

export interface AmbientHost {
  gameSessions: GameSessionPort;
  power: PowerPort;
  notify: (title: string, body: string) => void;
  translate: (key: string, vars?: Record<string, string>) => string;
}

/** Starts the Ambient domain at plugin load; the returned function tears it down completely. */
export function startAmbient(host: AmbientHost): () => void {
  const stopThemeImages = startThemeImages();
  let runtime: AmbientRuntime;
  try {
    runtime = new AmbientRuntime(host, ambientThemeChannel);
  } catch (error) {
    console.warn("[ambient:start_failed]", error);
    return stopThemeImages;
  }
  setAmbientRuntime(runtime);
  runtime.start().catch((error) => console.warn("[ambient:start_failed]", error));
  const sidePlayer = registerGlobal("PanelDeControlAmbientQamPlayer", QamSidePlayer);
  const floating = registerGlobal("PanelDeControlAmbientFloating", FloatingPlayer);
  return () => {
    floating();
    sidePlayer();
    setAmbientRuntime(null);
    runtime.stop();
    stopThemeImages();
  };
}

/** Theme pictures load on their own RPC, so they resolve with Ambiente's background off or its runtime down. */
function startThemeImages(): () => void {
  const images = new ThemeImages({
    list: () => getAmbientThemeImages(),
    register: (ref, owner, maxSide) => registerAmbientThemeImage(ref, owner, maxSide),
    keep: (owner, refs) => keepAmbientThemeImages(owner, refs),
  }, openThemeImagePicker);
  ambientThemeChannel.setImages(images);
  void images.refresh();
  return () => {
    ambientThemeChannel.setImages(null);
    images.stop();
  };
}
