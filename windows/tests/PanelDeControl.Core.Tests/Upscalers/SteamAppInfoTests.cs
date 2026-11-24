using System.Text;
using PanelDeControl.Core.Steam;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class SteamAppInfoTests
{
    [Theory]
    [InlineData(0x07564428u)]
    [InlineData(0x07564429u)]
    public void ReadsTheStoreTypeOfTheWantedApps(uint magic)
    {
        var file = Build(magic, (228980, "Tool"), (1245620, "Game"), (570, "Demo"));
        var found = new Dictionary<string, string>();
        SteamAppInfo.Read(new MemoryStream(file), new HashSet<string> { "228980", "1245620", "999" }, found);
        Assert.Equal(new Dictionary<string, string> { ["228980"] = "tool", ["1245620"] = "game" }, found);
    }

    [Fact]
    public void AnUnreadableFileFindsNothingInsteadOfFailing()
    {
        var found = new Dictionary<string, string>();
        SteamAppInfo.Read(new MemoryStream(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8 }), new HashSet<string> { "1" }, found);
        Assert.Empty(found);
        var cut = Build(0x07564429, (1, "Tool"));
        SteamAppInfo.Read(new MemoryStream(cut[..(cut.Length - 90)]), new HashSet<string> { "1" }, found);
        Assert.Empty(found);
    }

    private static byte[] Build(uint magic, params (uint AppId, string Type)[] apps)
    {
        var strings = new List<string> { "appinfo", "common", "type", "name" };
        var entries = new MemoryStream();
        using (var writer = new BinaryWriter(entries, Encoding.UTF8, leaveOpen: true))
        {
            foreach (var (appId, type) in apps)
            {
                var data = new MemoryStream();
                using (var body = new BinaryWriter(data, Encoding.UTF8, leaveOpen: true))
                {
                    body.Write(new byte[magic == 0x07564427 ? 40 : 60]);
                    Key(body, magic, strings, 0, "appinfo");
                    Key(body, magic, strings, 0, "common");
                    Key(body, magic, strings, 1, "name");
                    body.Write(Encoding.UTF8.GetBytes("Some name\0"));
                    Key(body, magic, strings, 1, "type");
                    body.Write(Encoding.UTF8.GetBytes(type + "\0"));
                    body.Write((byte)8);
                    body.Write((byte)8);
                    body.Write((byte)8);
                }

                writer.Write(appId);
                writer.Write((uint)data.Length);
                writer.Write(data.ToArray());
            }

            writer.Write(0u);
        }

        var output = new MemoryStream();
        using (var writer = new BinaryWriter(output, Encoding.UTF8, leaveOpen: true))
        {
            writer.Write(magic);
            writer.Write(1u);
            if (magic == 0x07564429)
            {
                writer.Write((long)(16 + entries.Length));
            }

            writer.Write(entries.ToArray());
            if (magic == 0x07564429)
            {
                writer.Write((uint)strings.Count);
                foreach (var text in strings)
                {
                    writer.Write(Encoding.UTF8.GetBytes(text + "\0"));
                }
            }
        }

        return output.ToArray();
    }

    private static void Key(BinaryWriter writer, uint magic, List<string> strings, byte kind, string key)
    {
        writer.Write(kind);
        if (magic == 0x07564429)
        {
            writer.Write(strings.IndexOf(key));
        }
        else
        {
            writer.Write(Encoding.UTF8.GetBytes(key + "\0"));
        }
    }
}
