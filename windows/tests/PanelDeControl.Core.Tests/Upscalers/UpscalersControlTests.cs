using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class UpscalersControlTests
{
    [Fact]
    public void RequestsRoundTripThroughTheWire()
    {
        var install = UpscalersWireCodec.DeserializeRequest(
            UpscalersWireCodec.SerializeRequest(UpscalersRequest.Install("1245620", "fsr-3.1", "performance", "int8", true)));
        Assert.Equal(UpscalersOperation.Install, install.Operation);
        Assert.Equal(("1245620", "fsr-3.1", "performance", "int8"), (install.AppId, install.Build, install.Quality, install.Model));
        Assert.True(install.ExperimentalEnabled);

        var plain = UpscalersWireCodec.DeserializeRequest(UpscalersWireCodec.SerializeRequest(UpscalersRequest.Overview()));
        Assert.Equal(UpscalersOperation.Overview, plain.Operation);
        Assert.False(plain.ExperimentalEnabled);
        Assert.Equal("{\"operation\":0}", UpscalersWireCodec.SerializeRequest(UpscalersRequest.Overview()));
    }

    [Theory]
    [InlineData("{\"operation\":\"overview\",\"appid\":\"1\"}")]
    [InlineData("{\"operation\":\"job\",\"experimental\":true}")]
    [InlineData("{\"operation\":\"game\"}")]
    [InlineData("{\"operation\":\"cover\"}")]
    [InlineData("{\"operation\":\"cover\",\"appid\":\"../1\"}")]
    [InlineData("{\"operation\":\"cover\",\"appid\":\"1\",\"build\":\"fsr-3.1\"}")]
    [InlineData("{\"operation\":\"game\",\"appid\":\"abc\"}")]
    [InlineData("{\"operation\":\"game\",\"appid\":\"123456789012345678901\"}")]
    [InlineData("{\"operation\":\"game\",\"appid\":\"1\",\"build\":\"fsr-3.1\"}")]
    [InlineData("{\"operation\":\"install\",\"appid\":\"1\"}")]
    [InlineData("{\"operation\":\"install\",\"appid\":\"1\",\"build\":\"..\\\\evil path\"}")]
    [InlineData("{\"operation\":\"install\",\"appid\":\"1\",\"build\":\"fsr-3.1\",\"quality\":\"a b\"}")]
    [InlineData("{\"operation\":\"uninstall\",\"appid\":\"1\",\"build\":\"fsr-3.1\"}")]
    [InlineData("{\"operation\":\"uninstall\"}")]
    [InlineData("{\"operation\":99}")]
    public void InvalidRequestsAreRefused(string payload)
    {
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void SettingsRequestsRoundTripThroughTheWire()
    {
        static UpscalersRequest Back(UpscalersRequest request) => UpscalersWireCodec.DeserializeRequest(UpscalersWireCodec.SerializeRequest(request));

        var configure = Back(UpscalersRequest.Configure("1245620", "balanced", "soft", true, "anr", "lite", true));
        Assert.Equal(UpscalersOperation.Configure, configure.Operation);
        Assert.Equal(("balanced", "soft", true, "anr", "lite"), (configure.Quality, configure.Sharpness, configure.FrameGen, configure.FrameGenRoute, configure.Model));
        Assert.True(configure.ExperimentalEnabled);
        Assert.Null(Back(UpscalersRequest.Configure("1", null, null, false, null, null, true)).FrameGen);

        Assert.Equal(UpscalersOperation.Ini, Back(UpscalersRequest.Ini("1245620")).Operation);

        var setIni = Back(UpscalersRequest.SetIni("1245620", "Menu.Scale", "1.5", true));
        Assert.Equal((UpscalersOperation.SetIni, "Menu.Scale", "1.5"), (setIni.Operation, setIni.Key, setIni.Value));
        Assert.Equal("Scale", Back(UpscalersRequest.SetIni("1", "Scale", "1.5", true)).Key);

        Assert.Equal(UpscalersOperation.Image, Back(UpscalersRequest.Image("1245620")).Operation);

        var image = Back(UpscalersRequest.SetImage("1245620", true, 0.25, "off", true));
        Assert.Equal((true, 0.25, "off"), (image.SharpnessEnabled, image.SharpnessValue, image.Int8));
        Assert.Equal("on", Back(UpscalersRequest.SetImage("1", null, null, "on", true)).Int8);
        var off = Back(UpscalersRequest.SetImage("1", false, 0, null, true));
        Assert.Equal((false, 0.0), (off.SharpnessEnabled, off.SharpnessValue));

        var restore = Back(UpscalersRequest.RestoreImage("1245620", true));
        Assert.Equal((UpscalersOperation.RestoreImage, true), (restore.Operation, restore.ExperimentalEnabled));

        var exe = Back(UpscalersRequest.SetExe("1245620", "Binaries/Win64/Game.exe", true));
        Assert.Equal((UpscalersOperation.SetExe, "Binaries/Win64/Game.exe", true), (exe.Operation, exe.Exe, exe.ExperimentalEnabled));
        Assert.Null(Back(UpscalersRequest.SetExe("1245620", null, true)).Exe);
        Assert.Equal(UpscalersOperation.Verify, Back(UpscalersRequest.Verify("1245620")).Operation);
        var cancel = Back(UpscalersRequest.Cancel(true));
        Assert.Equal((UpscalersOperation.Cancel, null, true), (cancel.Operation, cancel.AppId, cancel.ExperimentalEnabled));
        Assert.Equal(new[] { 13, 14, 15 }, new[] { UpscalersOperation.SetExe, UpscalersOperation.Verify, UpscalersOperation.Cancel }.Select(op => (int)op));
    }

    [Theory]
    [InlineData("{\"operation\":\"set_ini\",\"appid\":\"1\",\"value\":\"1\"}")]
    [InlineData("{\"operation\":\"set_ini\",\"appid\":\"1\",\"key\":\"Menu.Scale\"}")]
    [InlineData("{\"operation\":\"set_ini\",\"appid\":\"1\",\"key\":\"Menu.Scale\",\"value\":\"a\\nb\"}")]
    [InlineData("{\"operation\":\"set_ini\",\"appid\":\"1\",\"key\":\"Menu.Scale\",\"value\":\"1\",\"quality\":\"balanced\"}")]
    [InlineData("{\"operation\":\"set_image\",\"appid\":\"1\"}")]
    [InlineData("{\"operation\":\"set_image\",\"appid\":\"1\",\"sharpness_enabled\":true}")]
    [InlineData("{\"operation\":\"set_image\",\"appid\":\"1\",\"sharpness_value\":0.5}")]
    [InlineData("{\"operation\":\"set_image\",\"appid\":\"1\",\"int8\":\"max\"}")]
    [InlineData("{\"operation\":\"set_image\",\"appid\":\"1\",\"int8\":\"on\",\"key\":\"A.B\"}")]
    [InlineData("{\"operation\":\"configure\",\"appid\":\"1\",\"build\":\"fsr-3.1\"}")]
    [InlineData("{\"operation\":\"configure\",\"appid\":\"1\",\"key\":\"A.B\"}")]
    [InlineData("{\"operation\":\"configure\",\"appid\":\"1\",\"fg_route\":\"elsewhere\"}")]
    [InlineData("{\"operation\":\"ini\"}")]
    [InlineData("{\"operation\":\"ini\",\"appid\":\"1\",\"experimental\":true}")]
    [InlineData("{\"operation\":\"image\",\"appid\":\"1\",\"int8\":\"on\"}")]
    [InlineData("{\"operation\":\"restore_image\",\"appid\":\"1\",\"sharpness_enabled\":true}")]
    [InlineData("{\"operation\":\"install\",\"appid\":\"1\",\"build\":\"fsr-3.1\",\"key\":\"A.B\"}")]
    [InlineData("{\"operation\":\"set_exe\",\"exe\":\"Game.exe\"}")]
    [InlineData("{\"operation\":\"set_exe\",\"appid\":\"1\",\"exe\":\"Game.exe\",\"quality\":\"balanced\"}")]
    [InlineData("{\"operation\":\"set_exe\",\"appid\":\"1\",\"exe\":\"Game\u0000.exe\"}")]
    [InlineData("{\"operation\":\"install\",\"appid\":\"1\",\"build\":\"fsr-3.1\",\"exe\":\"Game.exe\"}")]
    [InlineData("{\"operation\":\"verify\"}")]
    [InlineData("{\"operation\":\"verify\",\"appid\":\"1\",\"experimental\":true}")]
    [InlineData("{\"operation\":\"verify\",\"appid\":\"1\",\"exe\":\"Game.exe\"}")]
    [InlineData("{\"operation\":\"cancel\",\"appid\":\"1\"}")]
    [InlineData("{\"operation\":\"cancel\",\"experimental\":true,\"build\":\"fsr-3.1\"}")]
    public void InvalidSettingsRequestsAreRefused(string payload)
    {
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void InvalidSettingsRequestsAreRefusedBeforeTheyAreSent()
    {
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetIni("1", "", "1", true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetIni("1", "Menu.Scale", "", true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetIni("1", "Menu.Scale", new string('9', UpscalerSettings.MaximumIniValueLength + 1), true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetImage("1", true, null, null, true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetImage("1", null, 0.5, null, true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetImage("1", null, null, "max", true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetImage("1", null, null, null, true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.Configure("1", "a b", null, false, null, null, true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetExe("1", "", true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.SetExe("1", new string('a', UpscalersRequest.MaximumExeLength + 1), true)));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.Configure("1", null, null, true, "elsewhere", null, true)));
    }

    [Fact]
    public void FieldsAreCappedInLength()
    {
        var longBuild = new string('a', UpscalersRequest.MaximumFieldLength + 1);
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.Install("1", longBuild, null, null, true)));
        Assert.Equal(1024, UpscalersWireCodec.MaximumRequestLength);
    }

    [Fact]
    public void ResponseCarriesTheStatusAndNeverAnOkWithAnError()
    {
        var rejected = UpscalersWireCodec.DeserializeResponse(UpscalersWireCodec.SerializeResponse(UpscalersResponse.Rejected("running")));
        Assert.Equal((UpscalersResponseStatus.Rejected, "running"), (rejected.Status, rejected.ErrorCode));

        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(
            new UpscalersResponse { Status = UpscalersResponseStatus.Ok, ErrorCode = "running" }));
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(
            new UpscalersResponse { Status = UpscalersResponseStatus.Fault }));
    }

    [Fact]
    public void OverviewAndJobRoundTripWithTheirFields()
    {
        var response = new UpscalersResponse
        {
            Status = UpscalersResponseStatus.Ok,
            Overview = new UpscalersOverview
            {
                Gpu = "rdna35",
                GpuSource = "name",
                Device = "rog_ally_x",
                SteamFound = true,
                Games = new[]
                {
                    new UpscalerGameSummary { AppId = "1", Name = "A", State = UpscalerGameStates.Installed, Build = "fsr-3.1", Version = "3.1", Running = false },
                    new UpscalerGameSummary { AppId = "2", Name = "B", State = UpscalerGameStates.Foreign, Updating = true, Scanned = false },
                },
            },
            Job = new UpscalerJobStatus { Id = "abc", Kind = "install", AppId = "1", State = UpscalerJobStates.Error, Stage = "download", DoneBytes = 5, TotalBytes = 10, Error = "running" },
        };

        var parsed = UpscalersWireCodec.DeserializeResponse(UpscalersWireCodec.SerializeResponse(response));

        Assert.Equal("rdna35", parsed.Overview!.Gpu);
        Assert.Equal(UpscalerGameStates.Installed, parsed.Overview.Games[0].State);
        Assert.False(parsed.Overview.Games[0].Running);
        Assert.Null(parsed.Overview.Games[1].Running);
        Assert.False(parsed.Overview.Games[1].Scanned);
        Assert.Equal(("download", 5L, 10L, "running"), (parsed.Job!.Stage, parsed.Job.DoneBytes, parsed.Job.TotalBytes, parsed.Job.Error));
    }

    [Fact]
    public void ResponsesOverTheLimitAreNeverSent()
    {
        var games = Enumerable.Range(1, 6000)
            .Select(index => new UpscalerGameSummary { AppId = index.ToString(), Name = new string('x', 100) })
            .ToArray();

        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(
            new UpscalersResponse { Status = UpscalersResponseStatus.Ok, Overview = new UpscalersOverview { Games = games } }));
    }

    [Fact]
    public void DuplicateGamesInAnOverviewAreRefused()
    {
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(new UpscalersResponse
        {
            Status = UpscalersResponseStatus.Ok,
            Overview = new UpscalersOverview
            {
                Games = new[] { new UpscalerGameSummary { AppId = "1" }, new UpscalerGameSummary { AppId = "1" } },
            },
        }));
    }

    [Fact]
    public void ACoverRequestNeedsOnlyANumericAppId()
    {
        var request = UpscalersWireCodec.DeserializeRequest(UpscalersWireCodec.SerializeRequest(UpscalersRequest.Cover("1245620")));
        Assert.Equal((UpscalersOperation.Cover, "1245620"), (request.Operation, request.AppId));
    }

    [Fact]
    public void ACoverTravelsInTheResponseWithinItsLimits()
    {
        var data = Convert.ToBase64String(new byte[UpscalersWireCodec.MaximumCoverBytes]);
        var ok = new UpscalersResponse { Status = UpscalersResponseStatus.Ok, Cover = new UpscalerCover { Mime = UpscalerCover.Jpeg, Data = data } };
        var back = UpscalersWireCodec.DeserializeResponse(UpscalersWireCodec.SerializeResponse(ok));
        Assert.Equal((UpscalerCover.Jpeg, data), (back.Cover!.Mime, back.Cover.Data));

        var tooBig = new UpscalerCover { Mime = UpscalerCover.Jpeg, Data = Convert.ToBase64String(new byte[UpscalersWireCodec.MaximumCoverBytes + 4096]) };
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(new UpscalersResponse { Status = UpscalersResponseStatus.Ok, Cover = tooBig }));
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(new UpscalersResponse { Status = UpscalersResponseStatus.Ok, Cover = new UpscalerCover { Mime = "text/html", Data = "AAAA" } }));
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(new UpscalersResponse { Status = UpscalersResponseStatus.Ok, Cover = new UpscalerCover { Mime = UpscalerCover.Png, Data = "" } }));
    }

    [Theory]
    [InlineData("fsr", "4.1.2", new[] { "lite", "full" }, null, "FSR 4.1.2 Lite")]
    [InlineData("fsr", "4.1.2", new[] { "lite", "full" }, "full", "FSR 4.1.2")]
    [InlineData("fsr", "3.1.5", new string[0], null, "FSR 3.1.5")]
    [InlineData("xess", "2", new string[0], null, "XeSS 2")]
    public void BuildsAreLabelledAsTheLinuxPillDoes(string family, string version, string[] models, string? model, string expected)
    {
        Assert.Equal(expected, UpscalerLabel.Badge(family, version, models, model));
    }
}
