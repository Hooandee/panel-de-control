// GPU generation, used to gate GPU-specific launch options (e.g. FSR4 picks a
// different Proton env var on RDNA3 vs RDNA4). Comes from the device profile.
// Which PROTON_* vars a Proton build supports is detected at runtime from the
// build's own script (see py_modules/launch/proton_caps.py), not guessed here.
export type GpuGen = "rdna2" | "rdna3" | "rdna35" | "rdna4" | "intel" | "unknown";
