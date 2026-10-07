using PanelDeControl.Core.Themes;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class ThemesContractTests
{
    [Fact]
    public void RequestsRoundTrip()
    {
        var requests = new[]
        {
            ThemesRequest.Get(),
            ThemesRequest.Install("hooandee-eclipse", "0.2.5"),
            ThemesRequest.SetEnabled("Hooandee Eclipse", true),
            ThemesRequest.SetOption("Hooandee Eclipse", "Acento", "Marte"),
            ThemesRequest.RestartSteam(),
        };

        foreach (var request in requests)
        {
            var decoded = ThemesWireCodec.DeserializeRequest(ThemesWireCodec.SerializeRequest(request));
            Assert.Equal(request.Operation, decoded.Operation);
            Assert.Equal(request.CatalogId, decoded.CatalogId);
            Assert.Equal(request.Name, decoded.Name);
            Assert.Equal(request.Enabled, decoded.Enabled);
            Assert.Equal(request.Value, decoded.Value);
        }
    }

    [Theory]
    [InlineData("{\"operation\":2}")]
    [InlineData("{\"operation\":3,\"name\":\"X\"}")]
    [InlineData("{\"operation\":0,\"name\":\"X\"}")]
    [InlineData("{\"operation\":99}")]
    public void MalformedRequestsAreRejected(string payload)
    {
        Assert.ThrowsAny<Exception>(() => ThemesWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void ResponsesRoundTripWithLocalizedOptions()
    {
        var response = new ThemesResponse
        {
            Status = ThemesResponseStatus.Ok,
            Connection = ThemesConnection.Connected,
            Themes = new[]
            {
                new ThemeEntry
                {
                    CatalogId = "hooandee-eclipse",
                    Name = "Hooandee Eclipse",
                    DisplayName = new[] { new LocalizedText("es", "Eclipse") },
                    InstalledVersion = "0.2.4",
                    PublishedVersion = "0.2.5",
                    Enabled = true,
                    PagesExpected = 4,
                    PagesApplied = 4,
                    RuntimeExpected = true,
                    RuntimeMounted = true,
                    Options = new[]
                    {
                        new ThemeOption(
                            "Acento",
                            new[] { new LocalizedText("es", "Color del tema"), new LocalizedText("en", "Theme color") },
                            "dropdown",
                            "Marte",
                            "Venus",
                            new[] { new ThemeOptionValue("Venus", new[] { new LocalizedText("en", "Venus") }), new ThemeOptionValue("Marte", new LocalizedText[0]) }),
                    },
                },
            },
        };

        var decoded = ThemesWireCodec.DeserializeResponse(ThemesWireCodec.SerializeResponse(response));

        var theme = Assert.Single(decoded.Themes);
        Assert.True(theme.Applied);
        Assert.True(theme.UpdateAvailable);
        Assert.Equal("Theme color", LocalizedText.Pick(theme.Options![0].Label, "en-GB"));
        Assert.Equal("Color del tema", LocalizedText.Pick(theme.Options[0].Label, "es"));
        Assert.Equal("Theme color", LocalizedText.Pick(theme.Options[0].Label, "de"));
        Assert.Null(LocalizedText.Pick(theme.Options[0].Values[1].Label, "es"));
    }

    [Fact]
    public void AppliedNeedsEveryPageAndTheRuntime()
    {
        var partial = new ThemeEntry { Name = "X", Enabled = true, PagesExpected = 4, PagesApplied = 3 };
        var noRuntime = new ThemeEntry { Name = "X", Enabled = true, PagesExpected = 1, PagesApplied = 1, RuntimeExpected = true };
        var nowhere = new ThemeEntry { Name = "X", Enabled = true };

        Assert.False(partial.Applied);
        Assert.False(noRuntime.Applied);
        Assert.False(nowhere.Applied);
    }

    [Fact]
    public void AFailedResponseMustCarryItsReason()
    {
        var response = new ThemesResponse { Status = ThemesResponseStatus.Rejected };

        Assert.Throws<InvalidDataException>(() => ThemesWireCodec.SerializeResponse(response));
    }
}
