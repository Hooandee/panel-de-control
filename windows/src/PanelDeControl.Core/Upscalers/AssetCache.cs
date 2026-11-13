using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;

namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// Downloads, verifies and unpacks catalog assets into Panel's cache, with the same layout and error codes as
/// <c>py_modules/upscalers/assets.py</c>: <c>root/sha256/filename</c>, the unpacked folder next to it and a
/// <c>.part-</c> file kept across attempts so a dropped download resumes.
/// </summary>
public sealed class AssetCache
{
    private const int Chunk = 256 * 1024;
    private const int Retries = 3;
    private static readonly TimeSpan[] Backoff = { TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(5) };
    private static readonly TimeSpan UnpackTimeout = TimeSpan.FromMinutes(5);
    private const string UserAgent = "panel-de-control-upscalers";

    private readonly HttpClient _http;
    private readonly string _tar;
    private readonly Func<string, long> _freeSpace;
    private readonly TimeSpan[] _backoff;

    /// <param name="tar">bsdtar: on Windows the system's own <c>System32\tar.exe</c>, which reads 7z, zip and tar.</param>
    public AssetCache(string root, string tar, HttpMessageHandler? handler = null, Func<string, long>? freeSpace = null, TimeSpan[]? backoff = null)
    {
        Root = root;
        _tar = tar;
        _http = handler is null ? new HttpClient() : new HttpClient(handler);
        _http.Timeout = TimeSpan.FromSeconds(30);
        _http.DefaultRequestHeaders.UserAgent.ParseAdd(UserAgent);
        _freeSpace = freeSpace ?? (path => new DriveInfo(Path.GetPathRoot(Path.GetFullPath(path))!).AvailableFreeSpace);
        _backoff = backoff ?? Backoff;
    }

    public string Root { get; }

    public string FilePath(UpscalerAsset asset) => Path.Combine(Root, asset.Sha256, asset.FileName);

    public string Unpacked(UpscalerAsset asset) => Path.Combine(Root, asset.Sha256, "unpacked");

    public string PartialPath(UpscalerAsset asset) => Path.Combine(Root, asset.Sha256, ".part-" + asset.FileName);

    public string MemberPath(UpscalerAsset asset)
    {
        var member = asset.Member ?? "";
        if (Path.IsPathRooted(member) || member.Split('/', '\\').Contains(".."))
        {
            throw new AssetException("unsafe_archive");
        }
        return Path.Combine(Unpacked(asset), member.Replace('/', Path.DirectorySeparatorChar));
    }

    public bool Ready(UpscalerAsset asset)
    {
        if (asset.Archive)
        {
            return File.Exists(Path.Combine(Unpacked(asset), ".complete"));
        }
        return File.Exists(asset.Member is null ? FilePath(asset) : MemberPath(asset));
    }

    /// <summary>The verified file, member or unpacked folder, fetched first when the cache lacks it.</summary>
    public async Task<string> EnsureAsync(UpscalerAsset asset, IProgress<long>? progress, CancellationToken cancel)
    {
        if (!Ready(asset))
        {
            await DownloadAsync(asset, progress, cancel).ConfigureAwait(false);
            if (asset.Archive || asset.Member is not null)
            {
                Unpack(asset);
                if (asset.Member is not null && !File.Exists(MemberPath(asset)))
                {
                    throw new AssetException("unpack_failed", "member missing");
                }
            }
        }
        else
        {
            progress?.Report(asset.Size);
        }
        if (asset.Archive)
        {
            return Unpacked(asset);
        }
        return asset.Member is null ? FilePath(asset) : MemberPath(asset);
    }

    public static string Sha256(string path) => GameFiles.Sha256(path);

    private async Task DownloadAsync(UpscalerAsset asset, IProgress<long>? progress, CancellationToken cancel)
    {
        var target = FilePath(asset);
        if (File.Exists(target) && new FileInfo(target).Length == asset.Size && Sha256(target) == asset.Sha256)
        {
            progress?.Report(asset.Size);
            return;
        }
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        CheckSpace(asset);
        var last = new AssetException("download_failed");
        foreach (var url in asset.Urls)
        {
            for (var attempt = 0; attempt < Retries; attempt++)
            {
                if (attempt > 0)
                {
                    try
                    {
                        await Task.Delay(_backoff[Math.Min(attempt - 1, _backoff.Length - 1)], cancel).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                        throw new AssetException("cancelled");
                    }
                }
                try
                {
                    await FetchAsync(url, asset, progress, cancel).ConfigureAwait(false);
                    if (File.Exists(target))
                    {
                        File.Delete(target);
                    }
                    File.Move(PartialPath(asset), target);
                    return;
                }
                catch (AssetException error)
                {
                    last = error;
                    if (error.Code is "cancelled" or "no_space")
                    {
                        throw;
                    }
                    File.Delete(PartialPath(asset));
                    break;
                }
                catch (OperationCanceledException) when (cancel.IsCancellationRequested)
                {
                    throw new AssetException("cancelled");
                }
                catch (Exception error) when (error is IOException or HttpRequestException or OperationCanceledException)
                {
                    var detail = error.GetType().Name + ": " + error.Message;
                    last = new AssetException("download_failed", detail.Length > 200 ? detail.Substring(0, 200) : detail);
                }
            }
        }
        throw last;
    }

    private void CheckSpace(UpscalerAsset asset)
    {
        var partial = PartialPath(asset);
        var have = File.Exists(partial) ? new FileInfo(partial).Length : 0;
        // Archives are unpacked next to the download, so they need room for both.
        var need = asset.Size - have + (asset.Archive || asset.Member is not null ? asset.Size * 2 : 0);
        var free = _freeSpace(Directory.Exists(Root) ? Root : Path.GetDirectoryName(Path.GetFullPath(Root))!);
        if (free < need)
        {
            throw new AssetException("no_space", (need - free).ToString(System.Globalization.CultureInfo.InvariantCulture));
        }
    }

    private async Task FetchAsync(string url, UpscalerAsset asset, IProgress<long>? progress, CancellationToken cancel)
    {
        var partial = PartialPath(asset);
        long have = File.Exists(partial) ? new FileInfo(partial).Length : 0;
        if (have >= asset.Size)
        {
            File.Delete(partial);
            have = 0;
        }
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        if (have > 0)
        {
            request.Headers.Range = new System.Net.Http.Headers.RangeHeaderValue(have, null);
        }
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancel).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException("HTTP " + (int)response.StatusCode);
        }
        if (have > 0 && response.StatusCode != HttpStatusCode.PartialContent)
        {
            have = 0;
        }
        using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var buffer = new byte[Chunk];
        if (have > 0)
        {
            using var existing = new FileStream(partial, FileMode.Open, FileAccess.Read, FileShare.Read, Chunk);
            int read;
            while ((read = existing.Read(buffer, 0, buffer.Length)) > 0)
            {
                digest.AppendData(buffer, 0, read);
            }
        }
        var received = have;
        progress?.Report(received);
        using (var source = await response.Content.ReadAsStreamAsync().ConfigureAwait(false))
        using (var output = new FileStream(partial, have > 0 ? FileMode.Append : FileMode.Create, FileAccess.Write, FileShare.None, Chunk))
        {
            while (true)
            {
                if (cancel.IsCancellationRequested)
                {
                    throw new AssetException("cancelled");
                }
                var read = await source.ReadAsync(buffer, 0, buffer.Length, cancel).ConfigureAwait(false);
                if (read == 0)
                {
                    break;
                }
                received += read;
                if (received > asset.Size)
                {
                    throw new AssetException("size_mismatch");
                }
                digest.AppendData(buffer, 0, read);
                output.Write(buffer, 0, read);
                progress?.Report(received);
            }
        }
        if (received != asset.Size)
        {
            throw new IOException($"stopped at {received} of {asset.Size} bytes");
        }
        if (Hex(digest.GetHashAndReset()) != asset.Sha256)
        {
            throw new AssetException("hash_mismatch");
        }
    }

    private void Unpack(UpscalerAsset asset)
    {
        var destination = Unpacked(asset);
        if (Directory.Exists(destination))
        {
            Directory.Delete(destination, true);
        }
        var staging = Path.Combine(Path.GetDirectoryName(destination)!, ".unpack-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try
        {
            Extract(FilePath(asset), staging);
            var root = Path.GetFullPath(staging) + Path.DirectorySeparatorChar;
            foreach (var path in Directory.GetFileSystemEntries(staging, "*", SearchOption.AllDirectories))
            {
                if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0
                    || !Path.GetFullPath(path).StartsWith(root, StringComparison.OrdinalIgnoreCase))
                {
                    throw new AssetException("unsafe_archive");
                }
            }
            File.WriteAllText(Path.Combine(staging, ".complete"), asset.Sha256);
            Directory.Move(staging, destination);
        }
        finally
        {
            if (Directory.Exists(staging))
            {
                Directory.Delete(staging, true);
            }
        }
    }

    /// <summary>bsdtar refuses absolute paths and <c>..</c> members by default; links are rejected afterwards.</summary>
    private void Extract(string archive, string destination)
    {
        if (!File.Exists(_tar))
        {
            throw new AssetException("unpack_failed", "tar missing");
        }
        var start = new ProcessStartInfo(_tar, "-xf " + Quote(archive) + " -C " + Quote(destination))
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
        };
        using var process = Process.Start(start) ?? throw new AssetException("unpack_failed", "tar did not start");
        var errors = process.StandardError.ReadToEndAsync();
        process.StandardOutput.ReadToEnd();
        if (!process.WaitForExit((int)UnpackTimeout.TotalMilliseconds))
        {
            try
            {
                process.Kill();
            }
            catch (InvalidOperationException)
            {
            }
            throw new AssetException("unpack_failed", "timeout");
        }
        if (process.ExitCode != 0)
        {
            var detail = errors.Result.Trim();
            throw new AssetException("unpack_failed", detail.Length > 200 ? detail.Substring(0, 200) : detail);
        }
    }

    private static string Quote(string path) => "\"" + path + "\"";

    private static string Hex(byte[] hash)
    {
        var text = new StringBuilder(hash.Length * 2);
        foreach (var value in hash)
        {
            text.Append(value.ToString("x2", System.Globalization.CultureInfo.InvariantCulture));
        }
        return text.ToString();
    }
}

public sealed class AssetException : Exception
{
    public AssetException(string code, string detail = "")
        : base(code)
    {
        Code = code;
        Detail = detail;
    }

    public string Code { get; }

    public string Detail { get; }
}
