import type { ClaimOwner } from "./types";

export interface ThemeClaim {
  id: string;
  name: string;
}

export interface ThirdPartySignal {
  confidence: "none" | "low" | "high";
  id?: string;
  candidates?: string[];
}

export interface ArbiterInput {
  themeClaims: ThemeClaim[];
  thirdParty: ThirdPartySignal;
  audioLoader: boolean;
  claims: Record<string, ClaimOwner>;
  previous: ClaimOwner | null;
}

export interface Conflict {
  kind: "theme" | "other" | "music";
  id: string;
  name: string | null;
}

export interface ArbiterDecision {
  background: ClaimOwner;
  music: "panel" | "other";
  conflict: Conflict | null;
}

export const AUDIO_LOADER_ID = "audioloader";

/** Decides who paints the background and who plays music. Doubt never raises a conflict. */
export function arbitrate(input: ArbiterInput): ArbiterDecision {
  let background: ClaimOwner = "panel";
  let conflict: Conflict | null = null;

  const theme = input.themeClaims[0];
  if (theme) {
    const choice = input.claims[theme.id];
    if (choice === "panel" || choice === "theme") background = choice;
    else {
      background = input.previous === "panel" ? "panel" : "theme";
      conflict = { kind: "theme", id: theme.id, name: theme.name };
    }
  } else if (input.thirdParty.confidence === "high" && input.thirdParty.id) {
    const choice = input.claims[input.thirdParty.id];
    if (choice === "other") background = "other";
    else if (choice !== "panel") conflict = { kind: "other", id: input.thirdParty.id, name: null };
  }

  let music: ArbiterDecision["music"] = "panel";
  if (input.audioLoader) {
    const choice = input.claims[AUDIO_LOADER_ID];
    if (choice !== "panel") music = "other";
    if (choice === undefined && conflict === null) {
      conflict = { kind: "music", id: AUDIO_LOADER_ID, name: "Audio Loader" };
    }
  }
  return { background, music, conflict };
}

export function conflictKey(conflict: Conflict | null): string | null {
  return conflict ? `${conflict.kind}:${conflict.id}` : null;
}
