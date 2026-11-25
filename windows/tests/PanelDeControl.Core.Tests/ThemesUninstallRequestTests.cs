using System.IO;
using PanelDeControl.Core.Themes;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class ThemesUninstallRequestTests
{
    [Fact]
    public void UninstallCarriesOnlyTheThemeName()
    {
        var request = ThemesWireCodec.DeserializeRequest(ThemesWireCodec.SerializeRequest(ThemesRequest.Uninstall("Hooandee Duo")));

        Assert.Equal(ThemesOperation.Uninstall, request.Operation);
        Assert.Equal("Hooandee Duo", request.Name);
        Assert.Null(request.CatalogId);
    }

    [Theory]
    [InlineData("{\"operation\":8}")]
    [InlineData("{\"operation\":8,\"name\":\"Hooandee Duo\",\"enabled\":true}")]
    public void UninstallWithoutANameOrWithOtherFieldsIsRejected(string payload)
    {
        Assert.Throws<InvalidDataException>(() => ThemesWireCodec.DeserializeRequest(payload));
    }
}
