using System.Text;
using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Upscalers;

/// <summary>Graphics API and version strings of a Windows executable, read from its PE headers.</summary>
public static class PeImage
{
    public static readonly IReadOnlyList<string> VersionKeys = new[]
    {
        "ProductName", "FileDescription", "CompanyName", "OriginalFilename", "FileVersion", "ProductVersion",
    };

    private const int ImportDirectory = 1;
    private const int DelayImportDirectory = 13;
    private const int MaxDlls = 512;
    private const int MaxResources = 8 * 1024 * 1024;
    private const int MaxNameBytes = 256;

    private static readonly (string Dll, string Api)[] GraphicsDlls =
    {
        ("d3d12.dll", "d3d12"),
        ("d3d11.dll", "d3d11"),
        ("vulkan-1.dll", "vulkan"),
        ("dxgi.dll", "dxgi"),
    };

    /// <summary>Lower-case names of every DLL the image imports, delay-loaded included.</summary>
    /// <exception cref="InvalidDataException">The image is not a PE or a table runs past its end.</exception>
    public static ISet<string> ImportedDlls(Stream image)
    {
        var reader = new ImageReader(image);
        var header = reader.PeHeader() ?? throw new InvalidDataException("not_pe");
        var optional = header.Offset + 24;
        var magic = reader.UInt16(optional);
        var directories = optional + (magic == 0x20B ? 112 : 96);
        for (var index = 0; index < header.Sections; index++)
        {
            var section = reader.Read(optional + header.OptionalSize + (index * 40L), 40);
            var virtualSize = BitConverter.ToUInt32(section, 8);
            var virtualAddress = BitConverter.ToUInt32(section, 12);
            var rawSize = BitConverter.ToUInt32(section, 16);
            var rawOffset = BitConverter.ToUInt32(section, 20);
            reader.Sections.Add((virtualAddress, Math.Max(virtualSize, rawSize), rawOffset));
        }

        var names = new HashSet<string>(StringComparer.Ordinal);
        foreach (var (directory, entrySize, nameField) in new[] { (ImportDirectory, 20, 12), (DelayImportDirectory, 32, 4) })
        {
            var entry = reader.Read(directories + (directory * 8L), 8);
            var rva = BitConverter.ToUInt32(entry, 0);
            var size = BitConverter.ToUInt32(entry, 4);
            var start = rva != 0 && size != 0 ? reader.Offset(rva) : null;
            if (start is null)
            {
                continue;
            }

            for (var index = 0; index < MaxDlls; index++)
            {
                var descriptor = reader.Read(start.Value + ((long)index * entrySize), entrySize);
                if (descriptor.All(value => value == 0))
                {
                    break;
                }

                var name = reader.String(BitConverter.ToUInt32(descriptor, nameField));
                if (!string.IsNullOrEmpty(name))
                {
                    names.Add(name!);
                }
            }
        }

        return names;
    }

    public static IReadOnlyList<string> GraphicsApis(Stream image)
    {
        ISet<string> names;
        try
        {
            names = ImportedDlls(image);
        }
        catch (InvalidDataException)
        {
            return Array.Empty<string>();
        }

        return GraphicsDlls
            .Where(item => names.Contains(item.Dll))
            .Select(item => item.Api)
            .OrderBy(api => api, StringComparer.Ordinal)
            .ToArray();
    }

    public static IReadOnlyList<string> GraphicsApis(IReadOnlyFileSystem fileSystem, string path) =>
        WithImage(fileSystem, path, GraphicsApis, Array.Empty<string>());

    /// <summary>ProductName and friends from the version resource; only the .rsrc section is read.</summary>
    public static IReadOnlyDictionary<string, string> VersionStrings(Stream image)
    {
        byte[] resources;
        try
        {
            resources = ResourceSection(new ImageReader(image));
        }
        catch (InvalidDataException)
        {
            return new Dictionary<string, string>();
        }

        var found = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var key in VersionKeys)
        {
            var needle = Encoding.Unicode.GetBytes(key + "\0");
            var start = 0;
            int index;
            while ((index = ByteSearch.IndexOf(resources, needle, start)) >= 6)
            {
                var header = index - 6;
                var valueWords = BitConverter.ToUInt16(resources, header + 2);
                var kind = BitConverter.ToUInt16(resources, header + 4);
                var value = index + needle.Length;
                value += (4 - ((value - header) % 4)) % 4;
                if (kind == 1 && valueWords > 0 && valueWords < 256)
                {
                    var available = Math.Max(0, Math.Min(valueWords * 2, resources.Length - value));
                    var text = value < resources.Length ? PythonText.Utf16(resources, value, available) : string.Empty;
                    text = PythonText.Strip(text.TrimEnd('\0'));
                    if (text.Length > 0)
                    {
                        found[key] = text;
                    }

                    break;
                }

                start = index + 1;
            }
        }

        return found;
    }

    public static IReadOnlyDictionary<string, string> VersionStrings(IReadOnlyFileSystem fileSystem, string path) =>
        WithImage(fileSystem, path, VersionStrings, new Dictionary<string, string>());

    private static byte[] ResourceSection(ImageReader reader)
    {
        var header = reader.PeHeader();
        if (header is null)
        {
            return Array.Empty<byte>();
        }

        var table = header.Offset + 24 + header.OptionalSize;
        for (var index = 0; index < header.Sections; index++)
        {
            var section = reader.Read(table + (index * 40L), 40);
            if (section[0] == '.' && section[1] == 'r' && section[2] == 's' && section[3] == 'r' && section[4] == 'c')
            {
                var rawSize = BitConverter.ToUInt32(section, 16);
                var rawOffset = BitConverter.ToUInt32(section, 20);
                return reader.Read(rawOffset, (int)Math.Min(rawSize, MaxResources));
            }
        }

        return Array.Empty<byte>();
    }

    private static T WithImage<T>(IReadOnlyFileSystem fileSystem, string path, Func<Stream, T> read, T fallback)
    {
        try
        {
            using var stream = fileSystem.OpenRead(path);
            return stream is null ? fallback : read(stream);
        }
        catch (IOException)
        {
            return fallback;
        }
        catch (UnauthorizedAccessException)
        {
            return fallback;
        }
    }

    private sealed class PeHeaderInfo
    {
        public PeHeaderInfo(long offset, int sections, int optionalSize)
        {
            Offset = offset;
            Sections = sections;
            OptionalSize = optionalSize;
        }

        public long Offset { get; }

        public int Sections { get; }

        public int OptionalSize { get; }
    }

    private sealed class ImageReader
    {
        private readonly Stream stream;

        public ImageReader(Stream stream)
        {
            this.stream = stream;
        }

        public List<(uint Virtual, uint Length, uint Raw)> Sections { get; } = new();

        public byte[] Read(long offset, int size)
        {
            if (offset < 0)
            {
                throw new InvalidDataException("truncated");
            }

            var data = ReadUpTo(offset, size);
            if (data.Length != size)
            {
                throw new InvalidDataException("truncated");
            }

            return data;
        }

        public ushort UInt16(long offset) => BitConverter.ToUInt16(Read(offset, 2), 0);

        /// <summary>The PE header position and its section counts, or null when the image is not a PE.</summary>
        public PeHeaderInfo? PeHeader()
        {
            var mz = Read(0, 2);
            if (mz[0] != 'M' || mz[1] != 'Z')
            {
                return null;
            }

            long offset = BitConverter.ToUInt32(Read(0x3C, 4), 0);
            var signature = Read(offset, 4);
            if (signature[0] != 'P' || signature[1] != 'E' || signature[2] != 0 || signature[3] != 0)
            {
                return null;
            }

            var counts = Read(offset + 6, 16);
            return new PeHeaderInfo(offset, BitConverter.ToUInt16(counts, 0), BitConverter.ToUInt16(counts, 14));
        }

        public long? Offset(uint rva)
        {
            foreach (var (virtualAddress, length, raw) in Sections)
            {
                if (virtualAddress <= rva && rva < (long)virtualAddress + length)
                {
                    return (long)raw + rva - virtualAddress;
                }
            }

            return null;
        }

        public string? String(uint rva)
        {
            var offset = Offset(rva);
            if (offset is null)
            {
                return null;
            }

            var raw = ReadUpTo(offset.Value, MaxNameBytes);
            var end = Array.IndexOf(raw, (byte)0);
            return PythonText.LowerAscii(raw, 0, end < 0 ? raw.Length : end);
        }

        private byte[] ReadUpTo(long offset, int size)
        {
            if (offset >= stream.Length)
            {
                return Array.Empty<byte>();
            }

            stream.Seek(offset, SeekOrigin.Begin);
            var data = new byte[size];
            var total = 0;
            while (total < size)
            {
                var read = stream.Read(data, total, size - total);
                if (read == 0)
                {
                    break;
                }

                total += read;
            }

            if (total != size)
            {
                Array.Resize(ref data, total);
            }

            return data;
        }
    }
}

internal static class ByteSearch
{
    public static int IndexOf(byte[] haystack, byte[] needle, int start)
    {
        if (needle.Length == 0)
        {
            return Math.Min(start, haystack.Length);
        }

        var last = haystack.Length - needle.Length;
        for (var index = Math.Max(0, start); index <= last; index++)
        {
            if (haystack[index] != needle[0])
            {
                continue;
            }

            var match = true;
            for (var offset = 1; offset < needle.Length; offset++)
            {
                if (haystack[index + offset] != needle[offset])
                {
                    match = false;
                    break;
                }
            }

            if (match)
            {
                return index;
            }
        }

        return -1;
    }
}
