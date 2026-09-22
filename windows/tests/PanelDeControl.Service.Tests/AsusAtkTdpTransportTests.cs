using System.Buffers.Binary;
using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class AsusAtkTdpTransportTests
{
    [Fact]
    public void DevsFrameUsesTheDocumentedLittleEndianLayout()
    {
        var frame = AsusAtkTdpTransport.BuildWriteFrame(
            AsusTdpRegister.Pl1Spl,
            25);

        Assert.Equal(16, frame.Length);
        Assert.Equal(0x53564544u, BinaryPrimitives.ReadUInt32LittleEndian(frame));
        Assert.Equal(8u, BinaryPrimitives.ReadUInt32LittleEndian(frame.AsSpan(4)));
        Assert.Equal(0x001200A3u, BinaryPrimitives.ReadUInt32LittleEndian(frame.AsSpan(8)));
        Assert.Equal(25u, BinaryPrimitives.ReadUInt32LittleEndian(frame.AsSpan(12)));
    }

    [Fact]
    public void DstsFrameIncludesAZeroSecondArgument()
    {
        var frame = AsusAtkTdpTransport.BuildReadFrame(AsusTdpRegister.Fppt);

        Assert.Equal(16, frame.Length);
        Assert.Equal(0x53545344u, BinaryPrimitives.ReadUInt32LittleEndian(frame));
        Assert.Equal(8u, BinaryPrimitives.ReadUInt32LittleEndian(frame.AsSpan(4)));
        Assert.Equal(0x001200C1u, BinaryPrimitives.ReadUInt32LittleEndian(frame.AsSpan(8)));
        Assert.Equal(0u, BinaryPrimitives.ReadUInt32LittleEndian(frame.AsSpan(12)));
    }

    [Theory]
    [InlineData(0x00010019u, 25)]
    [InlineData(0x00010023u, 35)]
    public void DstsCandidateAcceptsOnlyPresencePlusAReasonableValue(
        uint raw,
        int expectedWatts)
    {
        var result = AsusAtkTdpTransport.ParseDstsCandidate(raw);

        Assert.True(result.HasValue);
        Assert.Equal(expectedWatts, result.Watts);
    }

    [Theory]
    [InlineData(0x00000019u)]
    [InlineData(0x00030019u)]
    [InlineData(0xFFFFFFFFu)]
    [InlineData(0x00010100u)]
    public void AmbiguousDstsShapesAreUnavailable(uint raw)
    {
        Assert.False(AsusAtkTdpTransport.ParseDstsCandidate(raw).HasValue);
    }
}
