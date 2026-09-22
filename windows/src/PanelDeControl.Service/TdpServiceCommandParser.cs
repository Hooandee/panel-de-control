using PanelDeControl.Core.Controls;

namespace PanelDeControl.Service;

public readonly record struct TdpServiceCommand(
    TdpControlOperation Operation,
    int? RequestedWatts);

public static class TdpServiceCommandParser
{
    private const string SetPrefix = "set ";

    public static bool TryParse(
        string? text,
        out TdpServiceCommand command)
    {
        switch (text)
        {
            case "get":
                command = new TdpServiceCommand(TdpControlOperation.Get, null);
                return true;
            case "experimental on":
                command = new TdpServiceCommand(
                    TdpControlOperation.EnableExperimental,
                    null);
                return true;
            case "experimental off":
                command = new TdpServiceCommand(
                    TdpControlOperation.DisableExperimental,
                    null);
                return true;
        }

        if (text is null ||
            !text.StartsWith(SetPrefix, StringComparison.Ordinal))
        {
            command = default;
            return false;
        }

        var value = text.AsSpan(SetPrefix.Length);
        if (value.Length is < 1 or > 3 ||
            (value.Length > 1 && value[0] == '0'))
        {
            command = default;
            return false;
        }

        var watts = 0;
        foreach (var character in value)
        {
            if (character is < '0' or > '9')
            {
                command = default;
                return false;
            }

            watts = (watts * 10) + (character - '0');
        }

        command = new TdpServiceCommand(TdpControlOperation.Set, watts);
        return true;
    }
}
