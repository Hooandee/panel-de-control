type ClockPresentationInput = {
  manual: boolean;
  min: number | null;
  max: number | null;
  range_min: number | null;
  range_max: number | null;
  applied_min: number | null;
  applied_max: number | null;
  status: string;
};

export function gpuClockPresentation(state: ClockPresentationInput) {
  const rejected = state.status === "rejected";
  return {
    minimum: rejected
      ? (state.applied_min ?? state.min ?? state.range_min)
      : (state.min ?? state.range_min),
    maximum: rejected
      ? (state.applied_max ?? state.max ?? state.range_max)
      : (state.max ?? state.range_max),
    rejected,
  };
}
