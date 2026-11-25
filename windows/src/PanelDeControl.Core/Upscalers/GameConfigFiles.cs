using System.Text;
using System.Text.RegularExpressions;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What <see cref="GameConfigFiles.Apply"/> did to one setting, kept with the install so removal can put it back.</summary>
public sealed class GameConfigRecord
{
    public string File { get; set; } = "";

    public string Tag { get; set; } = "";

    public string Value { get; set; } = "";

    /// <summary><c>set</c>, <c>already</c>, <c>missing</c> (no file or element yet) or <c>failed</c>.</summary>
    public string State { get; set; } = "missing";

    public string? Before { get; set; }

    public string? Path { get; set; }
}

/// <summary>
/// Settings a recipe sets in the game's own XML config under the user's profile folder, undone on removal
/// (<c>py_modules/upscalers/game_config.py</c>). One element's text per entry, written in place so the rest of the file
/// stays byte for byte, and put back only while it still holds what Panel wrote.
/// </summary>
public static class GameConfigFiles
{
    private const int MaximumBytes = 512 * 1024;
    private static readonly UTF8Encoding Strict = new(false, true);

    public static IReadOnlyList<GameConfigRecord> Apply(string? profile, IEnumerable<GameConfigChange> entries)
    {
        var records = new List<GameConfigRecord>();
        foreach (var entry in entries)
        {
            var record = new GameConfigRecord { File = entry.File, Tag = entry.Element, Value = entry.Value };
            records.Add(record);
            var path = string.IsNullOrEmpty(profile) ? null : System.IO.Path.Combine(profile, entry.File.Replace('/', System.IO.Path.DirectorySeparatorChar));
            var text = path is null ? null : Read(path);
            var match = text is null ? null : Element(entry.Element).Match(text);
            if (path is null || text is null || match is null || !match.Success)
            {
                continue;
            }
            record.Before = match.Groups[2].Value;
            record.Path = path;
            if (match.Groups[2].Value == entry.Value)
            {
                record.State = "already";
                continue;
            }
            try
            {
                Write(path, text.Substring(0, match.Groups[2].Index) + entry.Value + text.Substring(match.Groups[2].Index + match.Groups[2].Length));
                record.State = "set";
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                record.State = "failed";
            }
        }
        return records;
    }

    public static void Restore(IEnumerable<GameConfigRecord> records)
    {
        foreach (var record in records)
        {
            var path = record.Path;
            if (record.State != "set" || path is null || path.Length == 0)
            {
                continue;
            }
            var text = Read(path);
            var match = text is null ? null : Element(record.Tag).Match(text);
            // The user (or the game) changed it since: theirs now.
            if (text is null || match is null || !match.Success || match.Groups[2].Value != record.Value)
            {
                continue;
            }
            try
            {
                Write(path, text.Substring(0, match.Groups[2].Index) + (record.Before ?? "") + text.Substring(match.Groups[2].Index + match.Groups[2].Length));
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    private static Regex Element(string tag) =>
        new("(<" + Regex.Escape(tag) + ">)([^<]{0,200})(</" + Regex.Escape(tag) + ">)", RegexOptions.CultureInvariant);

    private static string? Read(string path)
    {
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists || (info.Attributes & FileAttributes.ReparsePoint) != 0 || info.Length > MaximumBytes)
            {
                return null;
            }
            // Bytes, not a text reader: the game's line ends and any byte order mark stay as they are.
            return Strict.GetString(File.ReadAllBytes(path));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return null;
        }
    }

    private static void Write(string path, string text)
    {
        var temporary = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(path)!, "." + System.IO.Path.GetFileName(path) + ".pdc");
        File.WriteAllBytes(temporary, new UTF8Encoding(false).GetBytes(text));
        try
        {
            File.Replace(temporary, path, null);
        }
        finally
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
    }
}
