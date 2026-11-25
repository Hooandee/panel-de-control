using System.Text;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// Another tool's upscaler files that Panel moved aside, as Linux keeps it under <c>foreign_backup</c>. A copy of the
/// record sits in the backup folder so a restore survives Panel's state being wiped.
/// </summary>
public sealed class ForeignBackup
{
    public const string FileName = ".pdc-foreign.json";
    public const long MaximumBytes = 256 * 1024;

    private static readonly UTF8Encoding Utf8 = new(false);

    public string Dir { get; set; } = "";

    public string Target { get; set; } = "";

    public List<string> Items { get; set; } = new();

    /// <summary>Game libraries another tool replaced: their originals were put back and the replacements moved aside.</summary>
    public List<string> Swaps { get; set; } = new();

    /// <summary>Unix seconds.</summary>
    public double At { get; set; }

    public ForeignBackup Copy() => new() { Dir = Dir, Target = Target, Items = Items.ToList(), Swaps = Swaps.ToList(), At = At };

    public bool HasValidNames => Dir.Length > 0 && Target.Length > 0 && Items.Concat(Swaps).All(IsPlainName);

    public static bool IsPlainName(string name) =>
        name.Length > 0 && name is not ("." or "..") && Path.GetFileName(name) == name && name.IndexOfAny(new[] { '/', '\\', ':', '\0' }) < 0;

    internal DataObject ToData() => new(new[]
    {
        new KeyValuePair<string, DataValue>("dir", new DataString(Dir)),
        new KeyValuePair<string, DataValue>("target", new DataString(Target)),
        new KeyValuePair<string, DataValue>("items", new DataArray(Items.Select(item => (DataValue)new DataString(item)).ToList())),
        new KeyValuePair<string, DataValue>("swaps", new DataArray(Swaps.Select(item => (DataValue)new DataString(item)).ToList())),
        new KeyValuePair<string, DataValue>("at", new DataNumber(null, At)),
    });

    internal static ForeignBackup? FromData(DataValue? value)
    {
        if (value is not DataObject record || record.Get("dir") is not DataString { Value.Length: > 0 } dir
            || record.Get("target") is not DataString { Value.Length: > 0 } target)
        {
            return null;
        }

        return new ForeignBackup
        {
            Dir = dir.Value,
            Target = target.Value,
            Items = DataValue.StringItems(record.Get("items")).ToList(),
            Swaps = DataValue.StringItems(record.Get("swaps")).ToList(),
            At = record.Get("at") is DataNumber at ? at.Real : 0,
        };
    }

    /// <summary>Writes the record inside <see cref="Dir"/> through a temporary file.</summary>
    public void WriteSidecar()
    {
        var path = Path.Combine(Dir, FileName);
        var temporary = path + ".tmp";
        File.WriteAllText(temporary, PythonJson.Write(ToData()), Utf8);
        if (File.Exists(path))
        {
            File.Replace(temporary, path, null);
        }
        else
        {
            File.Move(temporary, path);
        }
    }

    /// <summary>The record kept in a backup folder, or null when there is none or it cannot be trusted.</summary>
    public static ForeignBackup? ReadSidecar(string folder)
    {
        try
        {
            var path = Path.Combine(folder, FileName);
            var info = new FileInfo(path);
            if (!info.Exists || info.Length > MaximumBytes || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                return null;
            }

            var record = FromData(DataValue.Parse(File.ReadAllText(path, Utf8)));
            return record is { HasValidNames: true } ? record : null;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DataFormatException)
        {
            return null;
        }
    }
}
