// GPU generation, used to gate GPU-specific launch options (e.g. FSR4 picks a
// different Proton env var on RDNA3 vs RDNA4). Comes from the device profile.
// Capabilities come from the installed Proton build (see proton_caps.py).
export type GpuGen = "rdna2" | "rdna3" | "rdna35" | "rdna4" | "intel" | "unknown";
