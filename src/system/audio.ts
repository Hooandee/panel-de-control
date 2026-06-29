import { ScalarControl } from "./types";

// SteamClient system-volume adapter. Volume is per audio device, so we track the
// default OUTPUT device: GetDevices() seeds the current level and device id,
// RegisterForDeviceVolumeChanged keeps it live, SetDeviceVolume writes it. The
// audioType channel is learned from the change event (Steam reports it) and
// defaults to 0 (output) for the first write. Isolated here and degrades to
// "unavailable" if the API is absent. CONFIRM the audioType on-device.
let outputDeviceId: number | null = null;
let outputAudioType = 0;

export const systemVolume: ScalarControl = {
  subscribe(cb) {
    const audio = SteamClient?.System?.Audio;
    if (!audio) return null;
    if (!audio.GetDevices || !audio.RegisterForDeviceVolumeChanged) return null;

    // Seed from the current default output device.
    audio
      .GetDevices()
      .then((info) => {
        const dev =
          info?.vecDevices?.find((d) => d.bIsDefaultOutputDevice && d.bHasOutput) ??
          info?.vecDevices?.find((d) => d.id === info.activeOutputDeviceId);
        if (dev) {
          outputDeviceId = dev.id;
          cb(dev.flOutputVolume);
        }
      })
      .catch(() => {
        /* devices unavailable */
      });

    let reg: { unregister: () => void } | null = null;
    try {
      const r = audio.RegisterForDeviceVolumeChanged((deviceId, audioType, volume) => {
        if (deviceId === outputDeviceId) {
          outputAudioType = audioType;
          cb(volume);
        }
      });
      if (r && typeof r.unregister === "function") reg = r;
    } catch {
      /* registration failed */
    }

    return reg
      ? () => {
          try {
            reg!.unregister();
          } catch {
            /* ignore */
          }
        }
      : null;
  },
  set(fraction) {
    try {
      if (outputDeviceId !== null) {
        void SteamClient?.System?.Audio?.SetDeviceVolume?.(
          outputDeviceId,
          outputAudioType,
          fraction,
        );
      }
    } catch {
      /* ignore */
    }
  },
};
