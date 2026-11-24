using System.Diagnostics;
using System.Text;
using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Steam;

/// <summary>
/// The store type Steam caches for an app (<c>game</c>, <c>tool</c>, <c>dlc</c>...) in <c>appcache/appinfo.vdf</c>:
/// the same fact the Linux section filters on (<c>app_type</c>), since an appmanifest does not say it.
/// </summary>
public static class SteamAppInfo
{
    public const string Tool = "tool";
    public static readonly TimeSpan Budget = TimeSpan.FromSeconds(3);

    private const uint MagicV39 = 0x07564427;
    private const uint MagicV40 = 0x07564428;
    private const uint MagicV41 = 0x07564429;
    private const int MaximumEntryBytes = 8 * 1024 * 1024;
    private const int MaximumDepth = 24;
    private const int MaximumStrings = 1_000_000;

    /// <summary>The lower-case type of each wanted app Steam has cached; apps it does not know are left out. Never throws.</summary>
    public static IReadOnlyDictionary<string, string> Types(IReadOnlyFileSystem fileSystem, IEnumerable<string> steamRoots, ISet<string> wanted)
    {
        var found = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var root in steamRoots)
        {
            using var stream = fileSystem.OpenRead(FileSystemPath.Join(root, "appcache/appinfo.vdf"));
            if (stream is null)
            {
                continue;
            }

            try
            {
                Read(stream, wanted, found);
            }
            catch (Exception error) when (error is IOException or EndOfStreamException or InvalidDataException or UnauthorizedAccessException or ArgumentException)
            {
            }

            if (wanted.All(found.ContainsKey))
            {
                break;
            }
        }

        return found;
    }

    public static void Read(Stream stream, ISet<string> wanted, IDictionary<string, string> found)
    {
        if (wanted.Count == 0 || !stream.CanSeek)
        {
            return;
        }

        using var reader = new BinaryReader(stream, Encoding.UTF8, leaveOpen: true);
        var magic = reader.ReadUInt32();
        if (magic is not (MagicV39 or MagicV40 or MagicV41))
        {
            return;
        }

        reader.ReadUInt32();
        string[]? strings = null;
        if (magic == MagicV41)
        {
            var tableOffset = reader.ReadInt64();
            var entries = stream.Position;
            if (tableOffset <= entries || tableOffset >= stream.Length)
            {
                return;
            }

            stream.Position = tableOffset;
            var count = reader.ReadUInt32();
            if (count > MaximumStrings)
            {
                return;
            }

            strings = new string[count];
            for (var index = 0; index < strings.Length; index++)
            {
                strings[index] = ReadCString(reader);
            }

            stream.Position = entries;
        }

        var clock = Stopwatch.StartNew();
        var headerBytes = magic == MagicV39 ? 40 : 60;
        while (true)
        {
            var appId = reader.ReadUInt32();
            if (appId == 0)
            {
                return;
            }

            var size = reader.ReadUInt32();
            var next = stream.Position + size;
            var id = appId.ToString(System.Globalization.CultureInfo.InvariantCulture);
            if (wanted.Contains(id) && size > headerBytes && size <= MaximumEntryBytes)
            {
                stream.Position += headerBytes;
                var data = reader.ReadBytes((int)size - headerBytes);
                if (CommonType(data, strings) is { } type)
                {
                    found[id] = type;
                    if (wanted.All(found.ContainsKey))
                    {
                        return;
                    }
                }
            }

            if (next > stream.Length || clock.Elapsed > Budget)
            {
                return;
            }

            stream.Position = next;
        }
    }

    private static string? CommonType(byte[] data, string[]? strings)
    {
        using var reader = new BinaryReader(new MemoryStream(data, writable: false), Encoding.UTF8);
        var path = new List<string>();
        string? type = null;
        try
        {
            Walk(reader, strings, path, 0, ref type);
        }
        catch (Exception error) when (error is EndOfStreamException or InvalidDataException or IndexOutOfRangeException)
        {
        }

        return type;
    }

    private static void Walk(BinaryReader reader, string[]? strings, List<string> path, int depth, ref string? type)
    {
        if (depth > MaximumDepth)
        {
            throw new InvalidDataException("appinfo nesting is too deep");
        }

        while (type is null)
        {
            var kind = reader.ReadByte();
            if (kind == 8)
            {
                return;
            }

            var key = strings is null ? ReadCString(reader) : strings[reader.ReadInt32()];
            switch (kind)
            {
                case 0:
                    path.Add(key);
                    Walk(reader, strings, path, depth + 1, ref type);
                    path.RemoveAt(path.Count - 1);
                    break;
                case 1:
                    var text = ReadCString(reader);
                    if (key == "type" && path.Count == 2 && path[0] == "appinfo" && path[1] == "common")
                    {
                        type = text.ToLowerInvariant();
                    }

                    break;
                case 2 or 3 or 4 or 6:
                    reader.ReadInt32();
                    break;
                case 5:
                    while (reader.ReadUInt16() != 0)
                    {
                    }

                    break;
                case 7 or 10:
                    reader.ReadInt64();
                    break;
                default:
                    throw new InvalidDataException("appinfo value type is unknown");
            }
        }
    }

    private static string ReadCString(BinaryReader reader)
    {
        var bytes = new List<byte>();
        while (reader.ReadByte() is var value && value != 0)
        {
            if (bytes.Count >= 4096)
            {
                throw new InvalidDataException("appinfo string is too long");
            }

            bytes.Add(value);
        }

        return Encoding.UTF8.GetString(bytes.ToArray());
    }
}
