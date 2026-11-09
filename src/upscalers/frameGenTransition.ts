export interface FrameGenStep { apply: () => Promise<void>; restore: () => Promise<void> }

export async function transitionFrameGen(steps: FrameGenStep[]): Promise<void> {
  const completed: FrameGenStep[] = [];
  try {
    for (const step of steps) { await step.apply(); completed.push(step); }
  } catch (error) {
    let failed = false;
    for (const step of completed.reverse()) {
      try { await step.restore(); } catch { failed = true; }
    }
    if (failed) throw new Error("fg_restore_failed");
    throw error;
  }
}
