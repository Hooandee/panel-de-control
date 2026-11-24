using System.Reflection;
using System.Runtime.Serialization;
using System.Text.Json;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class PlatformParityTests
{
    [Fact]
    public void EveryWidgetOperationIsInTheParityRegister()
    {
        using var parity = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "parity.json")));
        var listed = parity.RootElement.GetProperty("rpcs").EnumerateObject()
            .Where(rpc => rpc.Value.TryGetProperty("op", out _))
            .Select(rpc => rpc.Value.GetProperty("op").GetString()!)
            .Concat(parity.RootElement.GetProperty("windows_only_ops").EnumerateArray().Select(op => op.GetString()!))
            .ToHashSet(StringComparer.Ordinal);
        var operations = typeof(UpscalersOperation).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Select(field => field.GetCustomAttribute<EnumMemberAttribute>()!.Value!)
            .ToHashSet(StringComparer.Ordinal);

        Assert.Equal(operations.OrderBy(op => op, StringComparer.Ordinal), listed.OrderBy(op => op, StringComparer.Ordinal));
    }
}
