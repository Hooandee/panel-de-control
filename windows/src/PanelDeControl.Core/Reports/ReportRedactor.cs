using System;
using System.Text.RegularExpressions;

namespace PanelDeControl.Core.Reports;

/// <summary>
/// Removes what could identify a person or a single unit from report text, with the same rules as the
/// Linux collector (<c>py_modules/report/collector.py</c>) so both platforms send comparable bundles.
/// </summary>
public sealed class ReportRedactor
{
    private static readonly Regex ScrubbedKey = new(
        @"serial|uuid|\bmac\b|mac_?addr|hostname|host_name|^(?:user|username)$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex UserProfilePath = new(
        @"\b[A-Za-z]:\\(?:Users|Documents and Settings)\\[^\\\s""':;|]+",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex Mac = new(
        @"\b(?:[0-9a-fA-F]{2}[:_-]){5}[0-9a-fA-F]{2}\b",
        RegexOptions.CultureInvariant);

    private static readonly Regex Uuid = new(
        @"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        RegexOptions.CultureInvariant);

    private static readonly Regex SerialLabeled = new(
        @"((?:board|product|chassis|system|baseboard)?_?serial(?:\s*number)?)(\s*[:=]\s*)(\S+)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    // A long run that mixes letters and digits is the usual shape of a serial; pure words and pure
    // numbers (timestamps, builds) stay.
    private static readonly Regex SerialRun = new(
        @"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{8,}\b",
        RegexOptions.CultureInvariant);

    private readonly string? userProfile;
    private readonly Regex? hostName;

    public ReportRedactor(string? userProfile, string? hostName)
    {
        this.userProfile = string.IsNullOrWhiteSpace(userProfile) ? null : userProfile!.TrimEnd('\\');
        this.hostName = hostName is { Length: >= 3 }
            ? new Regex(@"\b" + Regex.Escape(hostName) + @"\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)
            : null;
    }

    /// <summary>The value of a key that names an identifier is dropped whole.</summary>
    public static bool IsIdentifierKey(string key) => ScrubbedKey.IsMatch(key);

    /// <param name="keepSerialRuns">
    /// For model-wide identifiers (firmware and driver versions, hardware ids) that look like serials
    /// but are shared by every unit and decide which bug applies.
    /// </param>
    public string Redact(string value, bool keepSerialRuns = false)
    {
        if (value.Length == 0)
        {
            return value;
        }

        if (userProfile is not null)
        {
            value = ReplaceIgnoringCase(value, userProfile, "~");
        }

        value = UserProfilePath.Replace(value, "~");
        if (hostName is not null)
        {
            value = hostName.Replace(value, "HOST");
        }

        value = Mac.Replace(value, "[mac]");
        value = Uuid.Replace(value, "[uuid]");
        value = SerialLabeled.Replace(value, match => match.Groups[1].Value + match.Groups[2].Value + "[serial]");
        return keepSerialRuns ? value : SerialRun.Replace(value, "[serial]");
    }

    private static string ReplaceIgnoringCase(string value, string search, string replacement)
    {
        var index = value.IndexOf(search, StringComparison.OrdinalIgnoreCase);
        while (index >= 0)
        {
            value = value.Substring(0, index) + replacement + value.Substring(index + search.Length);
            index = value.IndexOf(search, index + replacement.Length, StringComparison.OrdinalIgnoreCase);
        }

        return value;
    }
}
