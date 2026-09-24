namespace PanelDeControl.Core.Telemetry;

public static class SensorSelector
{
    public static SensorCandidate? Select(
        IEnumerable<SensorCandidate> candidates,
        HardwareKind hardwareKind,
        SensorKind sensorKind,
        IReadOnlyList<string> preferredNames)
    {
        if (candidates is null)
        {
            throw new ArgumentNullException(nameof(candidates));
        }

        if (preferredNames is null)
        {
            throw new ArgumentNullException(nameof(preferredNames));
        }

        return candidates
            .Select(candidate => new
            {
                Candidate = candidate,
                Preference = PreferenceRank(candidate.Name, preferredNames),
            })
            .Where(match =>
                match.Preference != int.MaxValue &&
                match.Candidate.HardwareKind == hardwareKind &&
                match.Candidate.SensorKind == sensorKind &&
                SensorPlausibility.IsPlausible(match.Candidate.SensorKind, match.Candidate.Value))
            .OrderBy(match => match.Preference)
            .ThenBy(match => match.Candidate.Identifier, StringComparer.Ordinal)
            .Select(match => match.Candidate)
            .FirstOrDefault();
    }

    private static int PreferenceRank(string name, IReadOnlyList<string> preferredNames)
    {
        for (var index = 0; index < preferredNames.Count; index++)
        {
            if (string.Equals(name, preferredNames[index], StringComparison.OrdinalIgnoreCase))
            {
                return index;
            }
        }

        return int.MaxValue;
    }
}
