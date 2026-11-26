using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class InGameBadgeTests : IDisposable
{
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);
    private readonly string root = Path.Combine(Path.GetTempPath(), "pdc-ingame-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void StartShowsForSixSecondsOncePerRun()
    {
        var policy = new InGameBadgePolicy();

        Assert.True(policy.Visible(Start, InGameModes.Start, "1:10", true));
        Assert.True(policy.Visible(Start.AddSeconds(5.9), InGameModes.Start, "1:10", true));
        Assert.False(policy.Visible(Start.AddSeconds(6), InGameModes.Start, "1:10", true));
        Assert.False(policy.Visible(Start.AddSeconds(60), InGameModes.Start, "1:10", true));
        Assert.True(policy.Visible(Start.AddSeconds(61), InGameModes.Start, "1:11", true));
    }

    [Fact]
    public void TheWindowWaitsForContentAndFollowsTheGameInFront()
    {
        var policy = new InGameBadgePolicy();

        Assert.False(policy.Visible(Start, InGameModes.Start, "1:10", false));
        Assert.True(policy.Visible(Start.AddSeconds(20), InGameModes.Start, "1:10", true));
        Assert.False(policy.Visible(Start.AddSeconds(21), InGameModes.Start, null, true));
        Assert.True(policy.Visible(Start.AddSeconds(22), InGameModes.Start, "1:10", true));
        Assert.False(policy.Visible(Start.AddSeconds(27), InGameModes.Start, "1:10", true));
    }

    [Fact]
    public void ComingBackToAGameDoesNotRestartItsWindowAfterAnotherGameStartedOne()
    {
        var policy = new InGameBadgePolicy();

        Assert.True(policy.Visible(Start, InGameModes.Start, "1:10", true));
        Assert.True(policy.Visible(Start.AddSeconds(1), InGameModes.Start, "2:20", true));
        Assert.False(policy.Visible(Start.AddSeconds(2), InGameModes.Start, "1:10", true));
    }

    [Fact]
    public void AlwaysShowsWhileTheGameIsInFrontAndOffNever()
    {
        var policy = new InGameBadgePolicy();

        Assert.True(policy.Visible(Start, InGameModes.Always, "1:10", true));
        Assert.True(policy.Visible(Start.AddHours(1), InGameModes.Always, "1:10", true));
        Assert.False(policy.Visible(Start.AddHours(1), InGameModes.Always, null, true));
        Assert.False(policy.Visible(Start.AddHours(1), InGameModes.Always, "1:10", false));
        Assert.False(policy.Visible(Start, InGameModes.Off, "2:20", true));
    }

    [Fact]
    public void ModesNormalizeToTheWindowsDefault()
    {
        Assert.Equal(InGameModes.Start, InGameModes.Normalize(null));
        Assert.Equal(InGameModes.Start, InGameModes.Normalize("sometimes"));
        Assert.Equal(InGameModes.Off, InGameModes.Normalize("off"));
        Assert.Equal(InGameModes.Always, InGameModes.Normalize("always"));
    }

    [Fact]
    public void FirstLineIsTheBuildLabelWithoutAResolutionPanelCannotFollowLive()
    {
        var lines = InGameContent.Lines(
            new InGameFacts { Label = "FSR 4.0.2", Active = true, RenderHeight = 720, OutputHeight = 1440 },
            new InGameText("en-US"));

        var span = Assert.Single(Assert.Single(lines).Spans);
        Assert.Equal(("FSR 4.0.2", BadgeTone.Normal), (span.Text, span.Tone));
    }

    [Fact]
    public void ALogProviderThatIsNotTheBuildsFamilyReplacesTheLabel()
    {
        var facts = new InGameFacts
        {
            Label = "FSR 4.0.2",
            Active = true,
            BuildFamily = "fsr",
            Observation = new ProviderObservation("xess", "XeSS", null, null, "optiscaler_log", "family_only"),
        };

        Assert.Equal("XeSS", InGameContent.Lines(facts, new InGameText("en"))[0].Spans[0].Text);

        facts.Observation = new ProviderObservation("fsr", "FSR", "4.0.2", "FP8", "optiscaler_log", "log_provider");
        Assert.Equal("FSR 4.0.2", InGameContent.Lines(facts, new InGameText("en"))[0].Spans[0].Text);
    }

    [Fact]
    public void AFallbackReplacesTheLabelInAmber()
    {
        var facts = new InGameFacts { Label = "FSR 4.0.2", Active = true, Fallback = new Fsr4Fallback("FSR 3.1", "backend_changed") };

        var span = InGameContent.Lines(facts, new InGameText("en"))[0].Spans[0];
        Assert.Equal(("FSR 4 not available in this game · using FSR 3.1", BadgeTone.Warn), (span.Text, span.Tone));

        facts.Fallback = new Fsr4Fallback(null, "vulkan_textures");
        Assert.Equal("FSR 4 no disponible en este juego", InGameContent.Lines(facts, new InGameText("es-ES"))[0].Spans[0].Text);
    }

    [Theory]
    [InlineData(true, "Generating frames")]
    [InlineData(false, "Paused")]
    [InlineData(null, "Configured")]
    public void FrameGenerationGetsASecondLineWithItsState(bool? generating, string state)
    {
        var facts = new InGameFacts { Label = "FSR 4.0.2", Active = true, FrameGen = true, FrameGenRoute = "anr", Generating = generating };

        var lines = InGameContent.Lines(facts, new InGameText("en"));

        Assert.Equal(2, lines.Count);
        Assert.Equal(new[] { "Apex ANR", state }, lines[1].Spans.Select(span => span.Text));
        Assert.Equal("OptiScaler", InGameContent.FrameGenName(null));
    }

    [Fact]
    public void ADllInstallShowsItsLabelWithoutALogAndAnIdleOneNothing()
    {
        Assert.Equal("FSR 3.1", InGameContent.Lines(new InGameFacts { Label = "FSR 3.1", Engine = "dll" }, new InGameText("en"))[0].Spans[0].Text);
        Assert.False(InGameContent.HasContent(new InGameFacts { Label = "FSR 3.1" }));
        Assert.Empty(InGameContent.Lines(new InGameFacts { Label = "FSR 3.1" }, new InGameText("en")));
        Assert.False(InGameContent.HasContent(null));
    }

    [Theory]
    [InlineData("de", "Pausiert")]
    [InlineData("fr-FR", "En pause")]
    [InlineData("it", "In pausa")]
    [InlineData("pt-BR", "Pausado")]
    [InlineData("ja-JP", "Paused")]
    [InlineData(null, "Paused")]
    public void TextsFollowTheLanguage(string? language, string paused)
    {
        Assert.Equal(paused, new InGameText(language).Paused);
    }

    [Fact]
    public void TheModeIsStoredAndKeptAcrossARestart()
    {
        var path = Path.Combine(root, "state.json");
        var store = new UpscalerStateStore(path);
        Assert.Equal(InGameModes.Start, store.InGameMode);

        store.SetInGameMode(InGameModes.Always);

        Assert.Equal(InGameModes.Always, new UpscalerStateStore(path).InGameMode);
        Assert.Contains("\"settings\"", File.ReadAllText(path));
    }

    [Fact]
    public void AFailedSaveKeepsTheModeAsItWas()
    {
        var store = new UpscalerStateStore(Path.Combine(root, "state.json"), (_, _) => throw new IOException("no"));

        Assert.Throws<IOException>(() => store.SetInGameMode(InGameModes.Off));
        Assert.Equal(InGameModes.Start, store.InGameMode);
    }

    [Fact]
    public void AnUnknownStoredModeFallsBackToTheDefault()
    {
        Directory.CreateDirectory(root);
        var path = Path.Combine(root, "state.json");
        File.WriteAllText(path, "{\"games\": {}, \"settings\": {\"ingame\": \"sometimes\"}}");

        Assert.Equal(InGameModes.Start, new UpscalerStateStore(path).InGameMode);
    }

    [Fact]
    public void TheOperationRoundTripsAndRefusesUnknownModesOrStrayFields()
    {
        var set = UpscalersWireCodec.DeserializeRequest(UpscalersWireCodec.SerializeRequest(UpscalersRequest.InGame(InGameModes.Always)));
        Assert.Equal((UpscalersOperation.InGame, InGameModes.Always), (set.Operation, set.Mode));
        Assert.Null(UpscalersWireCodec.DeserializeRequest(UpscalersWireCodec.SerializeRequest(UpscalersRequest.InGame())).Mode);

        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.InGame("sometimes")));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.DeserializeRequest("{\"operation\":6,\"appid\":\"1\"}"));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.DeserializeRequest("{\"operation\":0,\"mode\":\"off\"}"));
        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.DeserializeRequest("{\"operation\":2,\"appid\":\"1\",\"build\":\"fsr-3.1\",\"mode\":\"off\"}"));
    }

    [Fact]
    public void TheResponseCarriesTheModeAndRefusesAnUnknownOne()
    {
        var ok = new UpscalersResponse { Status = UpscalersResponseStatus.Ok, InGame = InGameModes.Off };
        Assert.Equal(InGameModes.Off, UpscalersWireCodec.DeserializeResponse(UpscalersWireCodec.SerializeResponse(ok)).InGame);

        Assert.ThrowsAny<Exception>(() => UpscalersWireCodec.SerializeResponse(new UpscalersResponse { Status = UpscalersResponseStatus.Ok, InGame = "x" }));
    }
}
