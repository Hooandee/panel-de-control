def decide(current_pl1, gpu_busy, min_w, max_w, step=2):
    """Next sustained PL1 (watts) for the auto-TDP loop.

    Ramps up when the GPU is saturated (>=95%), down when idle (<=70%), and holds
    in between. Clamped to [min_w, max_w]. When gpu_busy is None there is no
    signal — hold at the clamped current value and never guess.
    """
    cur = max(min_w, min(int(current_pl1), max_w))
    if gpu_busy is None:
        return cur
    if gpu_busy >= 95:
        nxt = cur + step
    elif gpu_busy <= 70:
        nxt = cur - step
    else:
        nxt = cur
    return max(min_w, min(nxt, max_w))
