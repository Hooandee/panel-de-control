using System.IO;
using PanelDeControl.Core.Themes;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class ThemesGameBarRequestTests
{
    [Fact]
    public void GameBarHiddenCarriesHowLongItWasShown()
    {
        var request = ThemesWireCodec.DeserializeRequest(ThemesWireCodec.SerializeRequest(ThemesRequest.GameBarHidden(412)));

        Assert.Equal(ThemesOperation.GameBarHidden, request.Operation);
        Assert.Equal(412, request.ShownMilliseconds);
    }

    [Fact]
    public void GameBarShownCarriesNothingButItsOperation()
    {
        var request = ThemesWireCodec.DeserializeRequest(ThemesWireCodec.SerializeRequest(ThemesRequest.GameBarShown()));

        Assert.Equal(ThemesOperation.GameBarShown, request.Operation);
        Assert.Null(request.Value);
        Assert.Throws<InvalidDataException>(() => ThemesWireCodec.DeserializeRequest("{\"operation\":10,\"value\":\"5\"}"));
    }

    [Theory]
    [InlineData("{\"operation\":11}")]
    [InlineData("{\"operation\":11,\"value\":\"-5\"}")]
    [InlineData("{\"operation\":11,\"value\":\"soon\"}")]
    [InlineData("{\"operation\":11,\"value\":\"5\",\"name\":\"Hooandee Vida\"}")]
    public void GameBarHiddenWithoutAValidDurationIsRejected(string payload)
    {
        Assert.Throws<InvalidDataException>(() => ThemesWireCodec.DeserializeRequest(payload));
    }
}
