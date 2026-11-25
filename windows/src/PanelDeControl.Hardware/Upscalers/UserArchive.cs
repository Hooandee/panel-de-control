using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>
/// Reads the archives a user brings. Zips are read in-process; everything else goes to 7-Zip when it is installed (it reads
/// every method and the passwords Patreon mods use) and to Windows' own <c>tar.exe</c> (bsdtar) otherwise, which cannot decrypt.
/// A protected archive without 7-Zip answers <c>password_unsupported</c>. Nothing inside an archive is ever run.
/// </summary>
public sealed class UserArchive : IUserArchive
{
    private static readonly TimeSpan ListTimeout = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan ExtractTimeout = TimeSpan.FromMinutes(10);
    private readonly string? _sevenZip;
    private readonly string? _tar;

    /// <param name="sevenZip">The full path of <c>7z.exe</c>, or null.</param>
    /// <param name="tar">The full path of bsdtar, or null.</param>
    public UserArchive(string? sevenZip, string? tar)
    {
        _sevenZip = sevenZip is not null && File.Exists(sevenZip) ? sevenZip : null;
        _tar = tar is not null && File.Exists(tar) ? tar : null;
    }

    public static UserArchive Locate(string? tar)
    {
        var candidates = new List<string>();
        foreach (var folder in new[] { Environment.SpecialFolder.ProgramFiles, Environment.SpecialFolder.ProgramFilesX86 })
        {
            var path = Environment.GetFolderPath(folder);
            if (path.Length > 0)
            {
                candidates.Add(Path.Combine(path, "7-Zip", "7z.exe"));
            }
        }

        candidates.AddRange((Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries)
            .Select(folder => Path.Combine(folder.Trim('"'), "7z.exe")));
        return new UserArchive(candidates.FirstOrDefault(File.Exists), tar);
    }

    public ArchiveListing List(string path, string? password)
    {
        if (path.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
        {
            var zip = ListZip(path);
            if (!zip.Encrypted || _sevenZip is null)
            {
                if (zip.Encrypted)
                {
                    throw new UserSourceException("password_unsupported");
                }

                return zip;
            }
        }

        if (_sevenZip is not null)
        {
            return ListSevenZip(path, password);
        }

        return ListTar(path);
    }

    public void Extract(string path, IReadOnlyList<KeyValuePair<string, string>> wanted, string destination, string? password)
    {
        Directory.CreateDirectory(destination);
        if (path.EndsWith(".zip", StringComparison.OrdinalIgnoreCase) && !ListZip(path).Encrypted)
        {
            ExtractZip(path, wanted, destination);
            return;
        }

        if (path.EndsWith(".zip", StringComparison.OrdinalIgnoreCase) && _sevenZip is null)
        {
            throw new UserSourceException("password_unsupported");
        }

        var staging = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(destination))!, ".unpack-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try
        {
            var full = Path.GetFullPath(path);
            var run = _sevenZip is not null
                ? Run(_sevenZip, new[] { "x", "-y", "-p" + (password ?? ""), "-o" + staging, full }, ExtractTimeout)
                : _tar is not null
                    ? Run(_tar, new[] { "-xf", full, "-C", staging }, ExtractTimeout)
                    : throw new UserSourceException("unreadable");
            if (run.ExitCode != 0)
            {
                throw Refusal(run, password);
            }

            var root = Path.GetFullPath(staging) + Path.DirectorySeparatorChar;
            foreach (var entry in Directory.EnumerateFileSystemEntries(staging, "*", SearchOption.AllDirectories))
            {
                if ((File.GetAttributes(entry) & FileAttributes.ReparsePoint) != 0)
                {
                    throw new UserSourceException("unsafe_archive");
                }
            }

            foreach (var pair in wanted)
            {
                var source = Path.GetFullPath(Path.Combine(staging, pair.Value.Replace('/', Path.DirectorySeparatorChar)));
                if (!source.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !File.Exists(source))
                {
                    throw new UserSourceException("unsafe_archive");
                }

                var target = Inside(destination, pair.Key);
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.Move(source, target, true);
            }
        }
        finally
        {
            UserFileStore.DeleteQuietly(staging);
        }
    }

    private static ArchiveListing ListZip(string path)
    {
        try
        {
            using var archive = ZipFile.OpenRead(path);
            var entries = new List<ArchiveEntry>();
            foreach (var entry in archive.Entries)
            {
                if (entry.FullName.EndsWith("/", StringComparison.Ordinal) || entry.FullName.EndsWith("\\", StringComparison.Ordinal))
                {
                    continue;
                }

                if (((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                {
                    throw new UserSourceException("unsafe_archive");
                }

                entries.Add(new ArchiveEntry(entry.FullName, entry.Length));
            }

            return new ArchiveListing(entries, ZipEncryption.Any(path));
        }
        catch (Exception error) when (error is InvalidDataException or IOException or NotSupportedException)
        {
            throw new UserSourceException("unreadable");
        }
    }

    private static void ExtractZip(string path, IReadOnlyList<KeyValuePair<string, string>> wanted, string destination)
    {
        try
        {
            using var archive = ZipFile.OpenRead(path);
            foreach (var pair in wanted)
            {
                var entry = archive.GetEntry(pair.Value) ?? throw new UserSourceException("unsafe_archive");
                var target = Inside(destination, pair.Key);
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                using var source = entry.Open();
                using var sink = new FileStream(target, FileMode.Create, FileAccess.Write, FileShare.None);
                source.CopyTo(sink);
            }
        }
        catch (Exception error) when (error is InvalidDataException or NotSupportedException)
        {
            throw new UserSourceException("unreadable");
        }
    }

    private ArchiveListing ListSevenZip(string path, string? password)
    {
        var run = Run(_sevenZip!, new[] { "l", "-slt", "-ba", "-p" + (password ?? ""), Path.GetFullPath(path) }, ListTimeout);
        if (run.ExitCode != 0)
        {
            throw Refusal(run, password);
        }

        var entries = new List<ArchiveEntry>();
        var encrypted = false;
        foreach (var block in run.Output.Replace("\r", "").Split(new[] { "\n\n" }, StringSplitOptions.None))
        {
            var fields = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var line in block.Split('\n'))
            {
                var index = line.IndexOf(" = ", StringComparison.Ordinal);
                if (index > 0)
                {
                    fields[line.Substring(0, index)] = line.Substring(index + 3);
                }
            }

            fields.TryGetValue("Path", out var name);
            fields.TryGetValue("Attributes", out var attributes);
            if (string.IsNullOrEmpty(name) || fields.GetValueOrDefault("Folder") == "+" || (attributes ?? "").StartsWith("D", StringComparison.Ordinal))
            {
                continue;
            }

            var space = (attributes ?? "").IndexOf(' ');
            var mode = space < 0 ? "" : attributes!.Substring(space + 1).TrimStart('-');
            if (mode.StartsWith("l", StringComparison.Ordinal) || fields.ContainsKey("Symbolic Link"))
            {
                throw new UserSourceException("unsafe_archive");
            }

            encrypted |= fields.GetValueOrDefault("Encrypted") == "+";
            entries.Add(new ArchiveEntry(name!, long.TryParse(fields.GetValueOrDefault("Size"), out var size) ? size : 0));
        }

        return new ArchiveListing(entries, encrypted);
    }

    private ArchiveListing ListTar(string path)
    {
        if (_tar is null)
        {
            throw new UserSourceException("unreadable");
        }

        var run = Run(_tar, new[] { "-tvf", Path.GetFullPath(path) }, ListTimeout);
        if (run.ExitCode != 0)
        {
            throw new UserSourceException("unreadable");
        }

        var entries = new List<ArchiveEntry>();
        foreach (var line in run.Output.Replace("\r", "").Split('\n'))
        {
            var fields = line.Split((char[]?)null, 9, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length < 9 || fields[0].StartsWith("d", StringComparison.Ordinal))
            {
                continue;
            }

            if (!fields[0].StartsWith("-", StringComparison.Ordinal))
            {
                throw new UserSourceException("unsafe_archive");
            }

            entries.Add(new ArchiveEntry(fields[8], long.TryParse(fields[4], out var size) ? size : 0));
        }

        // bsdtar cannot tell encryption apart in a listing; extracting then fails and says so.
        return new ArchiveListing(entries, false);
    }

    private static UserSourceException Refusal(ProcessResult run, string? password)
    {
        var said = (run.Output + run.Errors).ToLowerInvariant();
        return said.Contains("wrong password") || said.Contains("encrypted")
            ? new UserSourceException(string.IsNullOrEmpty(password) ? "password" : "password_wrong")
            : new UserSourceException("unreadable");
    }

    private static string Inside(string destination, string relative)
    {
        var root = Path.GetFullPath(destination) + Path.DirectorySeparatorChar;
        var target = Path.GetFullPath(Path.Combine(destination, relative.Replace('/', Path.DirectorySeparatorChar)));
        return target.StartsWith(root, StringComparison.OrdinalIgnoreCase) ? target : throw new UserSourceException("unsafe_archive");
    }

    private sealed class ProcessResult
    {
        public int ExitCode { get; set; }

        public string Output { get; set; } = "";

        public string Errors { get; set; } = "";
    }

    private static ProcessResult Run(string executable, IEnumerable<string> arguments, TimeSpan timeout)
    {
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            RedirectStandardInput = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var argument in arguments)
        {
            start.ArgumentList.Add(argument);
        }

        try
        {
            using var process = Process.Start(start) ?? throw new UserSourceException("unreadable");
            process.StandardInput.Close();
            var output = process.StandardOutput.ReadToEndAsync();
            var errors = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit((int)timeout.TotalMilliseconds))
            {
                try
                {
                    process.Kill(true);
                }
                catch (InvalidOperationException)
                {
                }

                throw new UserSourceException("unreadable");
            }

            return new ProcessResult { ExitCode = process.ExitCode, Output = output.Result, Errors = errors.Result };
        }
        catch (System.ComponentModel.Win32Exception)
        {
            throw new UserSourceException("unreadable");
        }
    }
}

/// <summary>Whether any file of a zip is encrypted, read from its central directory (the general purpose flag, bit 0).</summary>
internal static class ZipEncryption
{
    public static bool Any(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        using var reader = new BinaryReader(stream);
        var tail = (int)Math.Min(stream.Length, 22 + 65535);
        stream.Seek(-tail, SeekOrigin.End);
        var bytes = reader.ReadBytes(tail);
        var eocd = -1;
        for (var index = bytes.Length - 22; index >= 0; index--)
        {
            if (BitConverter.ToUInt32(bytes, index) == 0x06054b50)
            {
                eocd = index;
                break;
            }
        }

        if (eocd < 0)
        {
            throw new InvalidDataException("no end of central directory");
        }

        long entries = BitConverter.ToUInt16(bytes, eocd + 10);
        long offset = BitConverter.ToUInt32(bytes, eocd + 16);
        if (entries == 0xFFFF || offset == 0xFFFFFFFF)
        {
            var locator = eocd - 20;
            if (locator < 0 || BitConverter.ToUInt32(bytes, locator) != 0x07064b50)
            {
                throw new InvalidDataException("zip64 locator missing");
            }

            stream.Seek(BitConverter.ToInt64(bytes, locator + 8), SeekOrigin.Begin);
            var header = reader.ReadBytes(56);
            if (header.Length < 56 || BitConverter.ToUInt32(header, 0) != 0x06064b50)
            {
                throw new InvalidDataException("zip64 record missing");
            }

            entries = BitConverter.ToInt64(header, 32);
            offset = BitConverter.ToInt64(header, 48);
        }

        stream.Seek(offset, SeekOrigin.Begin);
        for (long index = 0; index < entries; index++)
        {
            var fixedPart = reader.ReadBytes(46);
            if (fixedPart.Length < 46 || BitConverter.ToUInt32(fixedPart, 0) != 0x02014b50)
            {
                throw new InvalidDataException("central directory is corrupt");
            }

            var flags = BitConverter.ToUInt16(fixedPart, 8);
            int name = BitConverter.ToUInt16(fixedPart, 28), extra = BitConverter.ToUInt16(fixedPart, 30), comment = BitConverter.ToUInt16(fixedPart, 32);
            var nameBytes = reader.ReadBytes(name);
            var directory = nameBytes.Length > 0 && nameBytes[nameBytes.Length - 1] == (byte)'/';
            if ((flags & 1) != 0 && !directory)
            {
                return true;
            }

            stream.Seek(extra + comment, SeekOrigin.Current);
        }

        return false;
    }
}
