import { ScalarControl } from "./types";

// SteamClient system-volume adapter. Volume is per audio device, so we track the
// default OUTPUT device: GetDevices() seeds the current level and device id,
// RegisterForDeviceVolumeChanged keeps it live, SetDeviceVolume writes it. The
// audioType channel is learned from the change event (defaults to 0 = output;
// confirmed on Ally X). NOTE: on real hardware RegisterForDeviceVolumeChanged
// registers but returns `undefined` (no unsubscribe handle) — so support is
// keyed off the METHOD existing, not off getting a handle. Never throws.
let outputDeviceId: number | null = null;
let outputAudioType = 0;

export const systemVolume: ScalarControl = {
  subscribe(cb) {
    try {
      const audio = SteamClient?.System?.Audio;
      if (
        !audio ||
        typeof audio.GetDevices !== "function" ||
        typeof audio.RegisterForDeviceVolumeChanged !== "function"
      ) {
        return null;
      }

      // Seed from the current default output device (volume only emits on change,
      // not on subscribe, so this is the source of the initial reading).
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

      const reg = audio.RegisterForDeviceVolumeChanged((deviceId, audioType, volume) => {
        if (deviceId === outputDeviceId) {
          outputAudioType = audioType;
          cb(volume);
        }
      });
      return () => {
        try {
          reg?.unregister?.();
        } catch {
          /* ignore */
        }
      };
    } catch {
      return null;
    }
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
