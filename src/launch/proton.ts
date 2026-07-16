// Proton version-family detection + GPU-based upscaler gating. Pure (no @decky)
// so it's unit-testable. We can't introspect which env vars a Proton build
// supports, so we map the game's compat tool to a FAMILY and curate per family.

export type ProtonFamily = "ge" | "experimental" | "cachyos" | "stable" | "unknown";

/**
 * Map a Steam compat-tool id (appDetailsStore.GetAppDetails().strCompatToolName)
 * to a family. Real values seen on-device: "GE-Proton10-21", "Proton-GE Latest",
 * "proton_10", "proton_11", "proton_experimental". Empty = Steam default → we
 * don't know the version, so treat as "unknown" (only base pills show).
 */
export function protonFamily(compatToolName: string | null | undefined): ProtonFamily {
  const s = (compatToolName ?? "").toLowerCase();
  if (!s) return "unknown";
  if (s.includes("cachyos") || s.includes("proton-em") || /(^|[-_ ])em([-_ ]|$)/.test(s)) return "cachyos";
  if (s.includes("ge-proton") || s.includes("proton-ge") || s.includes("ge_proton")) return "ge";
  if (s.includes("experimental")) return "experimental";
  if (s.includes("proton")) return "stable";
  return "unknown";
}

/** GPU generation for upscaler gating (from the device profile). */
export type GpuGen = "rdna2" | "rdna3" | "rdna35" | "rdna4" | "intel" | "unknown";

export type UpscalerTier = "fsr4" | "fsr3" | "xess";

/**
 * Whether an FSR/XeSS "upgrade" env var is worth offering on this GPU.
 * - FSR4: RDNA3 / RDNA4 only (not RDNA2 Deck, not officially RDNA3.5 iGPUs, not Intel).
 * - FSR3: broad AMD support (RDNA2+); not Intel.
 * - XeSS: cross-vendor, surfaced mainly for the Intel Claw.
 * On unknown GPU we stay conservative (offer FSR3 only) rather than promise FSR4.
 */
export function upscalerSupported(tier: UpscalerTier, gpu: GpuGen): boolean {
  switch (tier) {
    case "fsr4":
      return gpu === "rdna3" || gpu === "rdna4";
    case "fsr3":
      return gpu === "rdna2" || gpu === "rdna3" || gpu === "rdna35" || gpu === "rdna4";
    case "xess":
      return true;
  }
}
