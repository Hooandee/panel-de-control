using System.Formats.Tar;
using System.IO.Compression;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class AssetCacheTests : IDisposable
{
    private const string Tar = "/usr/bin/tar";
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-assets-" + Guid.NewGuid().ToString("N"));
    private static readonly TimeSpan[] NoWait = { TimeSpan.Zero };

    [Fact]
    public async Task DownloadsAndVerifiesIntoTheLinuxLayout()
    {
        var body = Bytes("proxy dll");
        var server = new FakeServer { ["https://a/x.dll"] = body };
        var asset = Asset("x.dll", body);
        var cache = Cache(server);

        var path = await cache.EnsureAsync(asset, null, CancellationToken.None);

        Assert.Equal(Path.Combine(_root, asset.Sha256, "x.dll"), path);
        Assert.Equal(body, File.ReadAllBytes(path));
        Assert.True(cache.Ready(asset));
        Assert.False(File.Exists(cache.PartialPath(asset)));
    }

    [Fact]
    public async Task ABadMirrorFallsThroughToTheNextOne()
    {
        var body = Bytes("good");
        var server = new FakeServer { ["https://a/x.dll"] = Bytes("evil"), ["https://b/x.dll"] = body };
        var asset = Asset("x.dll", body, "https://a/x.dll", "https://b/x.dll");

        var path = await Cache(server).EnsureAsync(asset, null, CancellationToken.None);

        Assert.Equal(body, File.ReadAllBytes(path));
    }

    [Fact]
    public async Task EveryMirrorWrongIsAHashMismatch()
    {
        var server = new FakeServer { ["https://a/x.dll"] = Bytes("evil") };
        var error = await Assert.ThrowsAsync<AssetException>(() => Cache(server).EnsureAsync(Asset("x.dll", Bytes("good")), null, CancellationToken.None));
        Assert.Equal("hash_mismatch", error.Code);
    }

    [Fact]
    public async Task ALongerBodyStopsAsSizeMismatch()
    {
        var body = Bytes("good");
        var server = new FakeServer { ["https://a/x.dll"] = Bytes("good and more") };
        var error = await Assert.ThrowsAsync<AssetException>(() => Cache(server).EnsureAsync(Asset("x.dll", body), null, CancellationToken.None));
        Assert.Equal("size_mismatch", error.Code);
    }

    [Fact]
    public async Task ADroppedDownloadResumesFromThePartialFile()
    {
        var body = Bytes("0123456789abcdef");
        var server = new FakeServer { ["https://a/x.dll"] = body };
        var asset = Asset("x.dll", body);
        var cache = Cache(server);
        Directory.CreateDirectory(Path.GetDirectoryName(cache.PartialPath(asset))!);
        File.WriteAllBytes(cache.PartialPath(asset), body.Take(6).ToArray());

        await cache.EnsureAsync(asset, null, CancellationToken.None);

        Assert.Equal(6, server.RangeStarts.Single());
        Assert.Equal(body, File.ReadAllBytes(cache.FilePath(asset)));
    }

    [Fact]
    public async Task AServerIgnoringTheRangeStartsOver()
    {
        var body = Bytes("0123456789abcdef");
        var server = new FakeServer { ["https://a/x.dll"] = body };
        server.IgnoreRange = true;
        var asset = Asset("x.dll", body);
        var cache = Cache(server);
        Directory.CreateDirectory(Path.GetDirectoryName(cache.PartialPath(asset))!);
        File.WriteAllBytes(cache.PartialPath(asset), Bytes("garbage"));

        await cache.EnsureAsync(asset, null, CancellationToken.None);

        Assert.Equal(body, File.ReadAllBytes(cache.FilePath(asset)));
    }

    [Fact]
    public async Task NetworkErrorsAreRetriedThenReported()
    {
        var server = new FakeServer { Failures = 5 };
        var error = await Assert.ThrowsAsync<AssetException>(() => Cache(server).EnsureAsync(Asset("x.dll", Bytes("good")), null, CancellationToken.None));
        Assert.Equal("download_failed", error.Code);
        Assert.Equal(3, server.Requests);
    }

    [Fact]
    public async Task CancellingStopsTheDownload()
    {
        var server = new FakeServer { ["https://a/x.dll"] = Bytes("good") };
        using var cancel = new CancellationTokenSource();
        cancel.Cancel();
        var error = await Assert.ThrowsAsync<AssetException>(() => Cache(server).EnsureAsync(Asset("x.dll", Bytes("good")), null, cancel.Token));
        Assert.Equal("cancelled", error.Code);
    }

    [Fact]
    public async Task NoRoomIsReportedBeforeDownloading()
    {
        var server = new FakeServer { ["https://a/x.dll"] = Bytes("good") };
        var cache = new AssetCache(_root, Tar, server, _ => 1, NoWait);
        var error = await Assert.ThrowsAsync<AssetException>(() => cache.EnsureAsync(Asset("x.dll", Bytes("good")), null, CancellationToken.None));
        Assert.Equal("no_space", error.Code);
        Assert.Equal(0, server.Requests);
    }

    [Fact]
    public async Task ArchivesUnpackWithBsdtar()
    {
        var zip = Zip(("OptiScaler.dll", "dll"), ("D3D12_Optiscaler/D3D12Core.dll", "core"));
        var server = new FakeServer { ["https://a/x.zip"] = zip };
        var asset = Asset("x.zip", zip, archive: true);

        var folder = await Cache(server).EnsureAsync(asset, null, CancellationToken.None);

        Assert.Equal("core", File.ReadAllText(Path.Combine(folder, "D3D12_Optiscaler", "D3D12Core.dll")));
        Assert.Equal(asset.Sha256, File.ReadAllText(Path.Combine(folder, ".complete")));
    }

    [Fact]
    public async Task AMemberComesFromItsArchive()
    {
        var tarball = TarGz(("4.1.2l-exact/amd_fidelityfx_upscaler_dx12.dll", "lite"), ("NOTICE.md", "n"));
        var server = new FakeServer { ["https://a/x.tar.gz"] = tarball };
        var asset = Asset("x.tar.gz", tarball, member: "4.1.2l-exact/amd_fidelityfx_upscaler_dx12.dll");
        var cache = Cache(server);

        var path = await cache.EnsureAsync(asset, null, CancellationToken.None);

        Assert.Equal("lite", File.ReadAllText(path));
        Assert.True(cache.Ready(asset));
    }

    [Fact]
    public async Task AMissingMemberIsAnUnpackFailure()
    {
        var zip = Zip(("other.dll", "x"));
        var server = new FakeServer { ["https://a/x.zip"] = zip };
        var error = await Assert.ThrowsAsync<AssetException>(() =>
            Cache(server).EnsureAsync(Asset("x.zip", zip, member: "missing.dll"), null, CancellationToken.None));
        Assert.Equal("unpack_failed", error.Code);
    }

    [Fact]
    public async Task AnArchiveEscapingItsFolderIsRefused()
    {
        var zip = Zip(("../escaped.dll", "x"));
        var server = new FakeServer { ["https://a/x.zip"] = zip };
        var cache = Cache(server);
        await Assert.ThrowsAsync<AssetException>(() => cache.EnsureAsync(Asset("x.zip", zip, archive: true), null, CancellationToken.None));
        Assert.False(File.Exists(Path.Combine(_root, "escaped.dll")));
        Assert.False(File.Exists(Path.Combine(Path.GetDirectoryName(cache.Unpacked(Asset("x.zip", zip, archive: true)))!, "escaped.dll")));
    }

    [Fact]
    public void AnUnsafeMemberNameIsRefused()
    {
        var asset = Asset("x.zip", Bytes("x"), member: "../x.dll");
        Assert.Equal("unsafe_archive", Assert.Throws<AssetException>(() => Cache(new FakeServer()).MemberPath(asset)).Code);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, true);
        }
    }

    private AssetCache Cache(FakeServer server) => new(_root, Tar, server, _ => long.MaxValue, NoWait);

    private static byte[] Bytes(string text) => Encoding.UTF8.GetBytes(text);

    private static UpscalerAsset Asset(string name, byte[] body, params string[] urls) => Asset(name, body, false, null, urls);

    private static UpscalerAsset Asset(string name, byte[] body, bool archive = false, string? member = null, params string[] urls) =>
        new(name, name, Convert.ToHexString(SHA256.HashData(body)).ToLowerInvariant(), body.Length,
            urls.Length > 0 ? urls : new[] { "https://a/" + name }, archive, member, 9);

    private static byte[] Zip(params (string Name, string Text)[] files)
    {
        using var memory = new MemoryStream();
        using (var archive = new ZipArchive(memory, ZipArchiveMode.Create, true))
        {
            foreach (var (name, text) in files)
            {
                using var stream = archive.CreateEntry(name).Open();
                stream.Write(Bytes(text));
            }
        }
        return memory.ToArray();
    }

    private static byte[] TarGz(params (string Name, string Text)[] files)
    {
        using var memory = new MemoryStream();
        using (var gzip = new GZipStream(memory, CompressionLevel.Fastest, true))
        using (var writer = new TarWriter(gzip))
        {
            foreach (var (name, text) in files)
            {
                writer.WriteEntry(new PaxTarEntry(TarEntryType.RegularFile, name) { DataStream = new MemoryStream(Bytes(text)) });
            }
        }
        return memory.ToArray();
    }

    private sealed class FakeServer : HttpMessageHandler
    {
        private readonly Dictionary<string, byte[]> _files = new();

        public byte[] this[string url]
        {
            set => _files[url] = value;
        }

        public bool IgnoreRange { get; set; }

        public int Failures { get; set; }

        public int Requests { get; private set; }

        public List<long> RangeStarts { get; } = new();

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests++;
            if (Failures-- > 0)
            {
                throw new HttpRequestException("connection reset");
            }
            if (!_files.TryGetValue(request.RequestUri!.ToString(), out var body))
            {
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
            }
            var from = request.Headers.Range?.Ranges.First().From;
            if (from is { } start && !IgnoreRange)
            {
                RangeStarts.Add(start);
                var response = new HttpResponseMessage(HttpStatusCode.PartialContent) { Content = new ByteArrayContent(body.Skip((int)start).ToArray()) };
                response.Content.Headers.ContentRange = new ContentRangeHeaderValue(start, body.Length - 1, body.Length);
                return Task.FromResult(response);
            }
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(body) });
        }
    }
}
