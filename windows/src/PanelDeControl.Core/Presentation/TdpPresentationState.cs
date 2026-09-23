using PanelDeControl.Core.Controls;

namespace PanelDeControl.Core.Presentation;

public sealed class TdpPresentationState
{
    public int SelectedWatts { get; private set; }

    public int? AppliedWatts { get; private set; }

    public void Select(int watts, int minimumWatts, int maximumWatts)
    {
        SelectedWatts = Math.Min(Math.Max(watts, minimumWatts), maximumWatts);
    }

    public void Observe(TdpControlResponse response)
    {
        if (response.Status == ControlStatus.Applied)
        {
            AppliedWatts = response.AppliedWatts;
        }

        if (response.MinimumWatts.HasValue && response.MaximumWatts.HasValue)
        {
            Select(response.TargetWatts ?? response.DefaultWatts ?? SelectedWatts,
                response.MinimumWatts.Value, response.MaximumWatts.Value);
        }
    }
}
