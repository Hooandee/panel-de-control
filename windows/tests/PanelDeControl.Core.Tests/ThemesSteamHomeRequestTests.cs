using System.IO;
using PanelDeControl.Core.Themes;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class ThemesSteamHomeRequestTests
{
    [Fact]
    public void SteamHomeCarriesNothingButItsOperation()
    {
        var request = ThemesWireCodec.DeserializeRequest(ThemesWireCodec.SerializeRequest(ThemesRequest.SteamHome()));

        Assert.Equal(ThemesOperation.SteamHome, request.Operation);
        Assert.Null(request.Name);
        Assert.Null(request.CatalogId);
    }

    [Fact]
    public void SteamHomeWithAThemeNameIsRejected()
    {
        Assert.Throws<InvalidDataException>(() => ThemesWireCodec.DeserializeRequest("{\"operation\":9,\"name\":\"Hooandee Vida\"}"));
    }
}
