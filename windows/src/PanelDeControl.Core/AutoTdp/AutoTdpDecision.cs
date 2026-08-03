namespace PanelDeControl.Core.AutoTdp;

public sealed class AutoTdpDecision
{
    public AutoTdpDecision(int nextPl1, int slackTicks)
    {
        NextPl1 = nextPl1;
        SlackTicks = slackTicks;
    }

    public int NextPl1 { get; }

    public int SlackTicks { get; }
}
