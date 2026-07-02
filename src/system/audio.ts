import { ScalarControl } from "./types";

// SteamClient system-volume adapter. Volume is per audio device, so we track the
// default OUTPUT device: GetDevices() seeds the current level and device id,
// RegisterForDeviceVolumeChanged keeps it live, SetDeviceVolume(id, audioType, v)
// writes it.
//
// The `audioType` arg to SetDeviceVolume is a DIRECTION, not a per-device config:
// CDP-probed on Claw, Steam Deck and both ROG Allys, audioType 1 = OUTPUT and
// audioType 0 = INPUT (mic). Writing the output volume with the wrong type hits the
// mic and is a silent no-op for the speaker. A previous version seeded it from the
// device's `currentConfig.eConfig`, which happens to be 1 on the Legion Go 2 (so it
// worked there by coincidence) but 0 on the Ally/Deck/Claw (so those wrote to the
// mic and the slider did nothing until a hardware volume-button event taught the
// real type). Output is audioType OUTPUT everywhere → write that, and only track
// OUTPUT change events (ignore mic-volume events so they can't corrupt the reading).
//
// NOTE: on real hardware RegisterForDeviceVolumeChanged registers but returns
// `undefined` (no unsubscribe handle) — so support is keyed off the METHOD existing,
// not off getting a handle. Never throws.
const OUTPUT = 1; // audioType for the output (speaker) channel
let outputDeviceId: number | null = null;

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
        // Only the OUTPUT channel drives the slider — ignore mic (input) events.
        if (deviceId === outputDeviceId && audioType === OUTPUT) {
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
        void SteamClient?.System?.Audio?.SetDeviceVolume?.(outputDeviceId, OUTPUT, fraction);
      }
    } catch {
      /* ignore */
    }
  },
};
