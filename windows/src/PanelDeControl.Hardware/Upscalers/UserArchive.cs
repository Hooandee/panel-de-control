using System.Diagnostics;
using System.IO.Compression;
using System.Security;
using System.Text;
using Microsoft.Win32;
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
    private const int CommandLineBudget = 24000;
    private readonly string? _sevenZip;
    private readonly string? _tar;

    /// <param name="sevenZip">The full path of <c>7z.exe</c>, or null.</param>
    /// <param name="tar">The full path of bsdtar, or null.</param>
    public UserArchive(string? sevenZip, string? tar)
    {
        _sevenZip = sevenZip is not null && File.Exists(sevenZip) ? sevenZip : null;
        _tar = tar is not null && File.Exists(tar) ? tar : null;
    }

    internal string? SevenZip => _sevenZip;

    public static UserArchive Locate(string? tar) => Locate(tar, ProgramFolders(), RegistryFolders());

    /// <summary>7-Zip is looked up only where its installer puts it: Program Files and the install path it records. Never PATH.</summary>
    internal static UserArchive Locate(string? tar, IEnumerable<string> programFolders, IEnumerable<string> registryFolders) =>
        new(FindSevenZip(programFolders.Select(folder => Path.Combine(folder, "7-Zip")).Concat(registryFolders)), tar);

    internal static string? FindSevenZip(IEnumerable<string> folders) =>
        folders.Where(folder => !string.IsNullOrWhiteSpace(folder)).Select(folder => Path.Combine(folder.Trim().Trim('"'), "7z.exe")).FirstOrDefault(File.Exists);

    private static IEnumerable<string> ProgramFolders() =>
        new[] { Environment.SpecialFolder.ProgramFiles, Environment.SpecialFolder.ProgramFilesX86 }
            .Select(Environment.GetFolderPath).Where(path => path.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase);

    private static IEnumerable<string> RegistryFolders()
    {
        var found = new List<string>();
        if (!OperatingSystem.IsWindows())
        {
            return found;
        }

        foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        {
            try
            {
                using var machine = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view);
                using var key = machine.OpenSubKey(@"SOFTWARE\7-Zip");
                foreach (var name in new[] { "Path64", "Path" })
                {
                    if (key?.GetValue(name) is string value && value.Length > 0)
                    {
                        found.Add(value);
                    }
                }
            }
            catch (Exception error) when (error is SecurityException or UnauthorizedAccessException or IOException or PlatformNotSupportedException)
            {
            }
        }

        return found;
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
        var listFile = staging + ".lst";
        Directory.CreateDirectory(staging);
        try
        {
            var full = Path.GetFullPath(path);
            var members = wanted.Select(pair => pair.Value).Distinct(StringComparer.Ordinal).ToList();
            if (members.Any(member => member.IndexOfAny(new[] { '\r', '\n', '\0' }) >= 0))
            {
                throw new UserSourceException("unsafe_archive");
            }

            if (_sevenZip is not null)
            {
                var passwordSwitch = PasswordSwitch(password);
                File.WriteAllLines(listFile, members, new UTF8Encoding(false));
                var run = Run(_sevenZip, new[] { "x", "-y", "-spd", "-sccUTF-8", "-scsUTF-8", "-i@" + listFile, passwordSwitch, "-o" + staging, full }, ExtractTimeout);
                if (run.ExitCode != 0)
                {
                    throw Refusal(run, password, true);
                }
            }
            else if (_tar is not null)
            {
                if (members.Any(member => member.Any(character => character > 0x7F)))
                {
                    throw new UserSourceException("name_unsupported");
                }

                foreach (var batch in Batches(members.Select(TarPattern)))
                {
                    var run = Run(_tar, new[] { "-xf", full, "-C", staging, "--" }.Concat(batch), ExtractTimeout);
                    if (run.ExitCode != 0)
                    {
                        throw Refusal(run, password, false);
                    }
                }
            }
            else
            {
                throw new UserSourceException("unreadable");
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
            try
            {
                File.Delete(listFile);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    /// <summary>7-Zip parses its own command line and does not honour an escaped quote, so such a password cannot be passed safely.</summary>
    private static string PasswordSwitch(string? password) =>
        password is not null && password.Contains('"') ? throw new UserSourceException("password_invalid") : "-p" + (password ?? "");

    /// <summary>bsdtar reads member names as glob patterns.</summary>
    private static string TarPattern(string member)
    {
        var text = new StringBuilder();
        foreach (var character in member)
        {
            if (character is '\\' or '*' or '?' or '[' or ']')
            {
                text.Append('\\');
            }

            text.Append(character);
        }

        return text.ToString();
    }

    private static IEnumerable<List<string>> Batches(IEnumerable<string> items)
    {
        var batch = new List<string>();
        var length = 0;
        foreach (var item in items)
        {
            if (batch.Count > 0 && length + item.Length + 3 > CommandLineBudget)
            {
                yield return batch;
                batch = new List<string>();
                length = 0;
            }

            batch.Add(item);
            length += item.Length + 3;
        }

        if (batch.Count > 0)
        {
            yield return batch;
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
        var run = Run(_sevenZip!, new[] { "l", "-slt", "-ba", "-sccUTF-8", PasswordSwitch(password), Path.GetFullPath(path) }, ListTimeout);
        if (run.ExitCode != 0)
        {
            throw Refusal(run, password, true);
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
            throw Refusal(run, null, false);
        }

        if (run.Output.Any(character => character > 0x7F))
        {
            throw new UserSourceException("name_unsupported");
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

    private static UserSourceException Refusal(ProcessResult run, string? password, bool canDecrypt)
    {
        var said = (run.Output + run.Errors).ToLowerInvariant();
        if (!said.Contains("wrong password") && !said.Contains("encrypted") && !said.Contains("passphrase") && !said.Contains("enter password"))
        {
            return new UserSourceException("unreadable");
        }

        return new UserSourceException(!canDecrypt ? "password_unsupported" : string.IsNullOrEmpty(password) ? "password" : "password_wrong");
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
