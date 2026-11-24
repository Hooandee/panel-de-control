using System.Numerics;
using System.Text.RegularExpressions;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>A catalog asset that follows its GitHub repository's newest release.</summary>
public sealed class ReleaseTrack
{
    public ReleaseTrack(string repo, string name, bool prerelease)
    {
        Repo = repo;
        Name = name;
        Prerelease = prerelease;
    }

    public string Repo { get; }

    /// <summary>Regular expression the whole asset file name must match.</summary>
    public string Name { get; }

    public bool Prerelease { get; }
}

/// <summary>
/// The newest official release of each tracked tool, verified by the SHA-256 digest GitHub publishes for it, with the
/// same rules, timings and cache file (<c>latest-releases.json</c>) as <c>py_modules/upscalers/latest.py</c>. The
/// catalog's pinned asset is the answer when the release list can't be read or carries no digest.
/// </summary>
public sealed class LatestReleases
{
    public static readonly TimeSpan Fresh = TimeSpan.FromHours(6);
    public static readonly TimeSpan Retry = TimeSpan.FromMinutes(10);
    private const int Limit = 8 * 1024 * 1024;
    private const long MaxSize = 1024L * 1024 * 1024;
    private const string UserAgent = "panel-de-control-upscalers";

    private readonly IReadOnlyDictionary<string, ReleaseTrack> _tracks;
    private readonly string _cacheFile;
    private readonly HttpClient _http;
    private readonly Func<DateTimeOffset> _clock;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private Dictionary<string, Known>? _memory;

    public LatestReleases(IReadOnlyDictionary<string, ReleaseTrack> tracks, string cacheFile, HttpMessageHandler? handler = null, Func<DateTimeOffset>? clock = null)
    {
        _tracks = tracks;
        _cacheFile = cacheFile;
        _clock = clock ?? (() => DateTimeOffset.UtcNow);
        _http = handler is null ? new HttpClient() : new HttpClient(handler);
        _http.Timeout = TimeSpan.FromSeconds(10);
        _http.DefaultRequestHeaders.UserAgent.ParseAdd(UserAgent);
        _http.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json");
    }

    public static string ApiUrl(string repo) => "https://api.github.com/repos/" + repo + "/releases?per_page=10";

    public bool Tracked(UpscalerAsset asset) => _tracks.ContainsKey(asset.Id);

    /// <summary>The build's archive at its newest verified version, or the catalog's pinned archive.</summary>
    public async Task<UpscalerAsset> ResolveArchiveAsync(BuildCatalog catalog, string buildId, CancellationToken cancel = default)
    {
        var build = catalog.Build(buildId) ?? throw new ArgumentException("unknown build", nameof(buildId));
        var pinned = catalog.Asset(build.Archive) ?? throw new ArgumentException("unknown archive", nameof(buildId));
        return await ResolveAsync(pinned, cancel).ConfigureAwait(false);
    }

    public async Task<UpscalerAsset> ResolveAsync(UpscalerAsset pinned, CancellationToken cancel = default)
    {
        if (!_tracks.TryGetValue(pinned.Id, out var track))
        {
            return pinned;
        }
        await _gate.WaitAsync(cancel).ConfigureAwait(false);
        try
        {
            var memory = Load();
            if (!memory.TryGetValue(pinned.Id, out var known))
            {
                known = memory[pinned.Id] = new Known();
            }
            var now = Seconds(_clock());
            if ((known.Checked is null || now - known.Checked.Value >= Fresh.TotalSeconds) && now - known.Failed >= Retry.TotalSeconds)
            {
                try
                {
                    var found = Newest(await FetchAsync(ApiUrl(track.Repo), cancel).ConfigureAwait(false), track);
                    known.Checked = now;
                    known.Failed = 0;
                    if (found is not null)
                    {
                        known.Release = found;
                    }
                }
                catch (Exception error) when (!cancel.IsCancellationRequested
                    && error is HttpRequestException or IOException or DataFormatException or InvalidOperationException or TaskCanceledException)
                {
                    known.Failed = now;
                }
                Save(memory);
            }
            var candidate = known.Release;
            if (candidate is null || candidate.Sha256 == pinned.Sha256)
            {
                return pinned;
            }
            return new UpscalerAsset(pinned.Id, candidate.FileName, candidate.Sha256, candidate.Size, new[] { candidate.Url },
                pinned.Archive, pinned.Member, pinned.Generation);
        }
        finally
        {
            _gate.Release();
        }
    }

    /// <summary>The release tag of the version this asset is, when it is the one resolved from GitHub.</summary>
    public string? Version(UpscalerAsset asset)
    {
        var release = Load().TryGetValue(asset.Id, out var known) ? known.Release : null;
        return release is not null && release.Sha256 == asset.Sha256 && release.Tag.Length > 0 ? release.Tag : null;
    }

    /// <summary>The newest published asset matching the track, with its digest; null when nothing qualifies.</summary>
    internal static Release? Newest(DataValue releases, ReleaseTrack track)
    {
        if (releases is not DataArray list)
        {
            return null;
        }
        var pattern = new Regex("^(?:" + track.Name + ")\\z", RegexOptions.CultureInvariant);
        var owner = "https://github.com/" + track.Repo + "/releases/download/";
        Release? best = null;
        foreach (var item in list.Items)
        {
            if (item is not DataObject release || Truthy(release.Get("draft")) || (Truthy(release.Get("prerelease")) && !track.Prerelease))
            {
                continue;
            }
            if (release.Get("assets") is not DataArray assets)
            {
                continue;
            }
            foreach (var entry in assets.Items)
            {
                if (entry is not DataObject asset)
                {
                    continue;
                }
                var name = Text(asset.Get("name"));
                var url = Text(asset.Get("browser_download_url"));
                if (!(asset.Get("size") is DataNumber { Integer: { } size } && size > 0 && size <= MaxSize)
                    || !pattern.IsMatch(name) || !url.StartsWith(owner, StringComparison.Ordinal) || !IsDigest(Text(asset.Get("digest"))))
                {
                    continue;
                }
                var published = Text(release.Get("published_at"));
                if (published.Length == 0)
                {
                    published = Text(asset.Get("updated_at"));
                }
                if (best is null || string.CompareOrdinal(published, best.Published) > 0)
                {
                    best = new Release(published, Text(release.Get("tag_name")), name, url, Text(asset.Get("digest")).Substring(7), (long)size);
                }
            }
        }
        return best;
    }

    private static bool IsDigest(string digest) =>
        digest.Length == 71 && digest.StartsWith("sha256:", StringComparison.Ordinal) && digest.Skip(7).All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static bool Truthy(DataValue? value) => value switch
    {
        DataBool flag => flag.Value,
        DataNumber number => number.Real != 0,
        DataString text => text.Value.Length > 0,
        DataArray array => array.Items.Count > 0,
        DataObject data => data.Count > 0,
        _ => false,
    };

    private static string Text(DataValue? value) => value is DataString text ? text.Value : "";

    private static double Seconds(DateTimeOffset moment) => moment.ToUnixTimeMilliseconds() / 1000.0;

    private async Task<DataValue> FetchAsync(string url, CancellationToken cancel)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancel).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException("HTTP " + (int)response.StatusCode);
        }
        using var source = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
        using var buffer = new MemoryStream();
        var chunk = new byte[64 * 1024];
        int read;
        while ((read = await source.ReadAsync(chunk, 0, chunk.Length, cancel).ConfigureAwait(false)) > 0)
        {
            buffer.Write(chunk, 0, read);
            if (buffer.Length > Limit)
            {
                throw new InvalidOperationException("release list too large");
            }
        }
        return DataValue.Parse(buffer.ToArray());
    }

    private Dictionary<string, Known> Load()
    {
        if (_memory is not null)
        {
            return _memory;
        }
        var loaded = new Dictionary<string, Known>(StringComparer.Ordinal);
        try
        {
            if (DataValue.Parse(File.ReadAllBytes(_cacheFile)) is DataObject root)
            {
                foreach (var member in root.Members)
                {
                    if (member.Value is DataObject entry)
                    {
                        loaded[member.Key] = Known.Read(entry);
                    }
                }
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or DataFormatException)
        {
            loaded.Clear();
        }
        return _memory = loaded;
    }

    private void Save(Dictionary<string, Known> memory)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(_cacheFile))!);
            var document = new DataObject(memory.Select(pair => new KeyValuePair<string, DataValue>(pair.Key, pair.Value.Write())).ToList());
            var temporary = _cacheFile + ".tmp";
            File.WriteAllText(temporary, PythonJson.Write(document), new System.Text.UTF8Encoding(false));
            if (File.Exists(_cacheFile))
            {
                File.Delete(_cacheFile);
            }
            File.Move(temporary, _cacheFile);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
    }

    internal sealed class Release
    {
        public Release(string published, string tag, string fileName, string url, string sha256, long size)
        {
            Published = published;
            Tag = tag;
            FileName = fileName;
            Url = url;
            Sha256 = sha256;
            Size = size;
        }

        public string Published { get; }

        public string Tag { get; }

        public string FileName { get; }

        public string Url { get; }

        public string Sha256 { get; }

        public long Size { get; }
    }

    private sealed class Known
    {
        public double? Checked { get; set; }

        public double Failed { get; set; }

        public Release? Release { get; set; }

        public static Known Read(DataObject entry)
        {
            var known = new Known
            {
                Checked = entry.Get("checked") is DataNumber checkedAt ? checkedAt.Real : null,
                Failed = entry.Get("failed") is DataNumber failed ? failed.Real : 0,
            };
            if (entry.Get("release") is DataObject release
                && release.Get("size") is DataNumber { Integer: { } size }
                && Text(release.Get("filename")) is { Length: > 0 } fileName && Text(release.Get("url")) is { Length: > 0 } url
                && Text(release.Get("sha256")) is { Length: 64 } sha256)
            {
                known.Release = new Release(Text(release.Get("published")), Text(release.Get("tag")), fileName, url, sha256, (long)size);
            }
            return known;
        }

        public DataValue Write()
        {
            var members = new List<KeyValuePair<string, DataValue>>();
            if (Release is { } release)
            {
                members.Add(new KeyValuePair<string, DataValue>("release", new DataObject(new[]
                {
                    new KeyValuePair<string, DataValue>("published", new DataString(release.Published)),
                    new KeyValuePair<string, DataValue>("tag", new DataString(release.Tag)),
                    new KeyValuePair<string, DataValue>("filename", new DataString(release.FileName)),
                    new KeyValuePair<string, DataValue>("url", new DataString(release.Url)),
                    new KeyValuePair<string, DataValue>("sha256", new DataString(release.Sha256)),
                    new KeyValuePair<string, DataValue>("size", new DataNumber(new BigInteger(release.Size), release.Size)),
                })));
            }
            if (Checked is { } checkedAt)
            {
                members.Add(new KeyValuePair<string, DataValue>("checked", new DataNumber(null, checkedAt)));
            }
            if (Failed > 0)
            {
                members.Add(new KeyValuePair<string, DataValue>("failed", new DataNumber(null, Failed)));
            }
            return new DataObject(members);
        }
    }
}
