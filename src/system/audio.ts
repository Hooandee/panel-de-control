import { ScalarControl } from "./types";

// SteamClient system-volume adapter. Volume is per audio device, so we track the
// default OUTPUT device: GetDevices() seeds the current level and device id,
// RegisterForDeviceVolumeChanged keeps it live, SetDeviceVolume(id, audioType, v)
// writes it.
//
// audioType is PER-DEVICE, not a constant: SetDeviceVolume must be called with the
// device's config type or the write hits the wrong channel and is silently a no-op
// (CDP-confirmed: Ally X = 0, Legion Go 2 = 1 = "Analog Stereo Duplex"). We seed it
// from the device's currentConfig.eConfig and keep learning it from change events
// (which carry the authoritative audioType). Seeding — not defaulting to 0 — is what
// makes the FIRST slider drag actually change the volume on devices whose type != 0
// (before this, volume only started working after an unrelated change event, e.g. a
// hardware volume-button press, taught us the right type).
//
// NOTE: on real hardware RegisterForDeviceVolumeChanged registers but returns
// `undefined` (no unsubscribe handle) — so support is keyed off the METHOD existing,
// not off getting a handle. Never throws.
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
            // Seed the write channel from the device config (Legion Go 2 = 1, not 0)
            // so the first set targets the right audioType; change events refine it.
            const eConfig = (dev as { currentConfig?: { eConfig?: number } }).currentConfig?.eConfig;
            if (typeof eConfig === "number") outputAudioType = eConfig;
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
