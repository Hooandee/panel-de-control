using System.Net;

namespace PanelDeControl.TestSupport;

internal static class TestTree
{
    public static void Write(string root, string relative, string text)
    {
        var path = Path.Combine(root, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
    }

    public static string Snapshot(string folder) => string.Join("\n", Directory
        .GetFileSystemEntries(folder, "*", SearchOption.AllDirectories)
        .OrderBy(path => path, StringComparer.Ordinal)
        .Select(path => path.Substring(folder.Length) + (File.Exists(path) ? "=" + File.ReadAllText(path) : "/")));
}

internal sealed class NoNetwork : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
        Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
}
