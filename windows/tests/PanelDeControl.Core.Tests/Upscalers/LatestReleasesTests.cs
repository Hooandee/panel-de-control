using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>The same cases tests/test_upscalers_latest.py replays against the Linux resolver.</summary>
public sealed class LatestReleasesTests : IDisposable
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "latest_releases.json")))!.AsObject();
    private readonly string _folder = Path.Combine(Path.GetTempPath(), "pdc-latest-" + Guid.NewGuid().ToString("N"));

    public static IEnumerable<object[]> CaseIds() => Fixture["cases"]!.AsArray().Select(node => new object[] { node!["id"]!.GetValue<string>() });

    public void Dispose()
    {
        if (Directory.Exists(_folder))
        {
            Directory.Delete(_folder, true);
        }
    }

    [Theory]
    [MemberData(nameof(CaseIds))]
    public async Task PickMatchesTheSharedCases(string id)
    {
        var fixture = Fixture["cases"]!.AsArray().Select(node => node!.AsObject()).Single(node => node["id"]!.GetValue<string>() == id);
        var track = (fixture["track"] ?? Fixture["track"])!.AsObject();
        var server = new FakeGitHub();
        var clock = Fixture["base_clock"]!.GetValue<long>();
        var latest = Releases(track, server, () => DateTimeOffset.FromUnixTimeSeconds(clock));
        foreach (var node in fixture["steps"]!.AsArray())
        {
            clock = Fixture["base_clock"]!.GetValue<long>() + node!["at"]!.GetValue<long>();
            server.Answer = node["response"]?.ToJsonString();
            var before = server.Requests.Count;
            var picked = await latest.ResolveAsync(Pinned());
            Assert.Equal(node["fetched"]!.GetValue<bool>(), server.Requests.Count - before == 1);
            Assert.All(server.Requests.Skip(before), url => Assert.Equal(Fixture["api_url"]!.GetValue<string>(), url));
            var expected = node["expected"]!.AsObject();
            if (expected["pinned"] is not null)
            {
                Assert.Equal(Pinned().Id, picked.Id);
                Assert.Equal((Pinned().FileName, Pinned().Sha256, Pinned().Size), (picked.FileName, picked.Sha256, picked.Size));
                Assert.Equal(Pinned().Urls, picked.Urls);
                continue;
            }
            Assert.Equal(expected["filename"]!.GetValue<string>(), picked.FileName);
            Assert.Equal(expected["sha256"]!.GetValue<string>(), picked.Sha256);
            Assert.Equal(expected["size"]!.GetValue<long>(), picked.Size);
            Assert.Equal(expected["urls"]!.AsArray().Select(url => url!.GetValue<string>()), picked.Urls);
            Assert.True(picked.Archive);
            Assert.Equal(expected["version"]!.GetValue<string>(), latest.Version(picked));
        }
    }

    [Fact]
    public async Task TheLastGoodReleaseSurvivesARestart()
    {
        var track = Fixture["track"]!.AsObject();
        var server = new FakeGitHub();
        var moment = DateTimeOffset.FromUnixTimeSeconds(Fixture["base_clock"]!.GetValue<long>());
        var first = Releases(track, server, () => moment);
        server.Answer = Fixture["cases"]!.AsArray()[0]!["steps"]![0]!["response"]!.ToJsonString();
        var picked = await first.ResolveAsync(Pinned());
        Assert.NotEqual(Pinned().Sha256, picked.Sha256);

        server.Answer = null;
        var second = Releases(track, server, () => moment.AddDays(2));
        Assert.Equal(picked.Sha256, (await second.ResolveAsync(Pinned())).Sha256);
    }

    [Fact]
    public async Task UntrackedAssetsAreNeverLookedUp()
    {
        var server = new FakeGitHub();
        var latest = Releases(Fixture["track"]!.AsObject(), server, () => DateTimeOffset.UtcNow);
        var other = new UpscalerAsset("not-tracked", "x.zip", new string('1', 64), 1, new[] { "https://example.com/x.zip" }, false, null, 9);
        Assert.Same(other, await latest.ResolveAsync(other));
        Assert.False(latest.Tracked(other));
        Assert.Empty(server.Requests);
    }

    [Fact]
    public void TheCatalogTracksLoadAsData()
    {
        var catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));
        var nightly = catalog.Tracks["optiscaler-10-nightly"];
        Assert.Equal("optiscaler/OptiScaler-nightly", nightly.Repo);
        Assert.True(nightly.Prerelease);
        Assert.False(catalog.Tracks["optiscaler-0.9.4"].Prerelease);
    }

    [Fact]
    public async Task TheBuildArchiveResolvesThroughItsTrack()
    {
        var catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));
        var pinned = catalog.Asset(catalog.Build("fsr-3.1")!.Archive)!;
        var server = new FakeGitHub { Answer = "[]" };
        var latest = new LatestReleases(catalog.Tracks, Path.Combine(_folder, "latest-releases.json"), server);
        Assert.Equal(pinned.Sha256, (await latest.ResolveArchiveAsync(catalog, "fsr-3.1")).Sha256);
        Assert.Equal("https://api.github.com/repos/optiscaler/OptiScaler/releases?per_page=10", Assert.Single(server.Requests));
    }

    private LatestReleases Releases(JsonObject track, FakeGitHub server, Func<DateTimeOffset> clock)
    {
        var tracks = new Dictionary<string, ReleaseTrack>
        {
            [Pinned().Id] = new(track["repo"]!.GetValue<string>(), track["name"]!.GetValue<string>(), track["prerelease"]!.GetValue<bool>()),
        };
        return new LatestReleases(tracks, Path.Combine(_folder, "latest-releases.json"), server, clock);
    }

    private static UpscalerAsset Pinned()
    {
        var pinned = Fixture["pinned"]!;
        return new UpscalerAsset(pinned["id"]!.GetValue<string>(), pinned["filename"]!.GetValue<string>(), pinned["sha256"]!.GetValue<string>(),
            pinned["size"]!.GetValue<long>(), new[] { pinned["url"]!.GetValue<string>() }, true, null, 9);
    }

    [Fact]
    public async Task AResponseBodyThatNeverEndsIsCutAtTheDeadlineAndFallsBackToThePinnedAsset()
    {
        var tracks = new Dictionary<string, ReleaseTrack> { [Pinned().Id] = new("acme/tool", @"Tool_\d+\.\d+\.zip", false) };
        var latest = new LatestReleases(tracks, Path.Combine(_folder, "latest-releases.json"), new HangingBody(), () => DateTimeOffset.FromUnixTimeSeconds(1_000_000),
            TimeSpan.FromMilliseconds(300));

        var watch = System.Diagnostics.Stopwatch.StartNew();
        var picked = await latest.ResolveAsync(Pinned());

        Assert.Equal(Pinned().Sha256, picked.Sha256);
        Assert.True(watch.Elapsed < TimeSpan.FromSeconds(8), watch.Elapsed.ToString());
    }

    [Fact]
    public async Task OnlyAPlainFileNameIsTrustedFromTheRelease()
    {
        var tracks = new Dictionary<string, ReleaseTrack> { [Pinned().Id] = new("acme/tool", @".*\.zip", false) };
        var owner = "https://github.com/acme/tool/releases/download/v1/";
        string Entry(string name, char digit, string published) =>
            "{\"tag_name\":\"v1\",\"published_at\":\"" + published + "\",\"assets\":[{\"name\":" + System.Text.Json.JsonSerializer.Serialize(name)
            + ",\"size\":10,\"digest\":\"sha256:" + new string(digit, 64) + "\",\"browser_download_url\":\"" + owner + "x.zip\"}]}";
        var answer = "[" + string.Join(",", Entry("..\\evil.zip", 'a', "2030-01-04"), Entry("sub/evil.zip", 'b', "2030-01-03"), Entry("C:evil.zip", 'c', "2030-01-02"),
            Entry("ok.zip", 'd', "2030-01-01")) + "]";
        var latest = new LatestReleases(tracks, Path.Combine(_folder, "latest-releases.json"), new FakeGitHub { Answer = answer }, () => DateTimeOffset.FromUnixTimeSeconds(1_000_000));

        var picked = await latest.ResolveAsync(Pinned());

        Assert.Equal(("ok.zip", new string('d', 64)), (picked.FileName, picked.Sha256));
        var none = new LatestReleases(tracks, Path.Combine(_folder, "other.json"),
            new FakeGitHub { Answer = "[" + Entry("..\\evil.zip", 'a', "2030-01-04") + "]" }, () => DateTimeOffset.FromUnixTimeSeconds(1_000_000));
        Assert.Equal(Pinned().Sha256, (await none.ResolveAsync(Pinned())).Sha256);
    }

    [Fact]
    public async Task ARejectedReleaseIsNotOfferedAgain()
    {
        var track = Fixture["track"]!.AsObject();
        var server = new FakeGitHub();
        var clock = Fixture["base_clock"]!.GetValue<long>();
        var latest = Releases(track, server, () => DateTimeOffset.FromUnixTimeSeconds(clock));
        server.Answer = Fixture["cases"]!.AsArray()[0]!["steps"]![0]!["response"]!.ToJsonString();
        var picked = await latest.ResolveAsync(Pinned());
        Assert.NotEqual(Pinned().Sha256, picked.Sha256);

        latest.Reject(picked.Sha256);

        Assert.Equal(Pinned().Sha256, (await latest.ResolveAsync(Pinned())).Sha256);
        Assert.Empty(latest.TakeSuperseded());
    }

    private sealed class HangingBody : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(new Hanging()) });

        private sealed class Hanging : Stream
        {
            public override bool CanRead => true;

            public override bool CanSeek => false;

            public override bool CanWrite => false;

            public override long Length => throw new NotSupportedException();

            public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }

            public override void Flush()
            {
            }

            public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();

            public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken) => new TaskCompletionSource<int>().Task;

            public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();

            public override void SetLength(long value) => throw new NotSupportedException();

            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }
    }

    private sealed class FakeGitHub : HttpMessageHandler
    {
        public string? Answer { get; set; }

        public List<string> Requests { get; } = new();

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests.Add(request.RequestUri!.ToString());
            if (Answer is null)
            {
                throw new HttpRequestException("offline");
            }
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(Answer, Encoding.UTF8, "application/json") });
        }
    }
}
