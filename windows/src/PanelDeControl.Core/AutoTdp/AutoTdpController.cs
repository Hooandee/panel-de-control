using System;
using System.Collections.Generic;
using System.Linq;

namespace PanelDeControl.Core.AutoTdp;

public static class AutoTdpController
{
    private const double UpGpu = 97;
    private const double DownGpu = 88;
    private const int RecentSamples = 2;
    private const int SlackHold = 6;
    private const double DownGain = 1.0 / 3.0;

    public static AutoTdpDecision Decide(
        int currentPl1,
        IReadOnlyList<double?> gpuWindow,
        int slackTicks,
        int minWatts,
        int maxWatts,
        int upStep = 2,
        int downStep = 1,
        int maxDownStep = 5)
    {
        var current = Clamp(currentPl1, minWatts, maxWatts);
        var gpu = gpuWindow.Where(value => value.HasValue).Select(value => value!.Value).ToArray();
        if (gpu.Length == 0)
        {
            return new AutoTdpDecision(current, slackTicks);
        }

        if (gpu.Skip(Math.Max(0, gpu.Length - RecentSamples)).Max() >= UpGpu)
        {
            return new AutoTdpDecision(Clamp(current + upStep, minWatts, maxWatts), 0);
        }

        var average = gpu.Average();
        if (average > DownGpu)
        {
            return new AutoTdpDecision(current, 0);
        }

        var slack = slackTicks + 1;
        if (slack < SlackHold)
        {
            return new AutoTdpDecision(current, slack);
        }

        var gap = DownGpu - average;
        var step = (int)Math.Round(gap * DownGain, MidpointRounding.ToEven);
        step = Clamp(step, downStep, maxDownStep);
        return new AutoTdpDecision(Math.Max(minWatts, current - step), 0);
    }

    private static int Clamp(int value, int minimum, int maximum)
    {
        return Math.Max(minimum, Math.Min(maximum, value));
    }
}
