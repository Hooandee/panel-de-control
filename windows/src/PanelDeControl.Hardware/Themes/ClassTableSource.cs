using System.Net.Http;

namespace PanelDeControl.Hardware.Themes;

public interface IClassTableSource
{
    IReadOnlyList<IReadOnlyList<string>>? Current(bool betaClient);
}

/// <summary>
/// The community class-name table CSS Loader uses (api.deckthemes.com), cached on disk and
/// refreshed in the background at most once a day. Lookups never wait for the network.
/// </summary>
public sealed class ClassTableSource : IClassTableSource, IDisposable
{
    private const long MaximumBytes = 16L * 1024 * 1024;
    private static readonly TimeSpan RefreshAfter = TimeSpan.FromHours(24);
    private static readonly TimeSpan RetryAfter = TimeSpan.FromMinutes(10);

    private readonly string cacheDirectory;
    private readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(30) };
    private readonly object gate = new();
    private readonly Dictionary<bool, (IReadOnlyList<IReadOnlyList<string>>? Table, DateTime CheckedUtc, Task? Refresh)> channels = new();

    public ClassTableSource(string cacheDirectory)
    {
        this.cacheDirectory = cacheDirectory;
    }

    public IReadOnlyList<IReadOnlyList<string>>? Current(bool betaClient)
    {
        lock (gate)
        {
            if (!channels.TryGetValue(betaClient, out var channel))
            {
                channel = (ReadCache(betaClient), DateTime.MinValue, null);
            }

            var age = DateTime.UtcNow - CacheTime(betaClient);
            var due = channel.Refresh is null
                && DateTime.UtcNow - channel.CheckedUtc > RetryAfter
                && (channel.Table is null || age > RefreshAfter);
            if (due)
            {
                channel.CheckedUtc = DateTime.UtcNow;
                channel.Refresh = Task.Run(() => RefreshAsync(betaClient));
            }

            channels[betaClient] = channel;
            return channel.Table;
        }
    }

    public void Dispose() => http.Dispose();

    private string CachePath(bool beta) => Path.Combine(cacheDirectory, beta ? "css_translations.beta.json" : "css_translations.json");

    private DateTime CacheTime(bool beta) =>
        File.Exists(CachePath(beta)) ? File.GetLastWriteTimeUtc(CachePath(beta)) : DateTime.MinValue;

    private IReadOnlyList<IReadOnlyList<string>>? ReadCache(bool beta)
    {
        try
        {
            var path = CachePath(beta);
            return File.Exists(path) && new FileInfo(path).Length <= MaximumBytes
                ? ClassTranslator.ParseTable(File.ReadAllText(path))
                : null;
        }
        catch (Exception exception) when (exception is IOException or FormatException or System.Text.Json.JsonException)
        {
            CompanionLog.Write("themes.class_table_cache", exception);
            return null;
        }
    }

    private async Task RefreshAsync(bool beta)
    {
        IReadOnlyList<IReadOnlyList<string>>? table = null;
        try
        {
            var url = beta ? "https://api.deckthemes.com/beta.json" : "https://api.deckthemes.com/stable.json";
            using var response = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            if (response.Content.Headers.ContentLength > MaximumBytes)
            {
                throw new InvalidDataException("Class table is too large");
            }

            var text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            table = ClassTranslator.ParseTable(text);
            if (table.Count == 0)
            {
                throw new InvalidDataException("Class table is empty");
            }

            Directory.CreateDirectory(cacheDirectory);
            var temporary = CachePath(beta) + ".tmp";
            await File.WriteAllTextAsync(temporary, text).ConfigureAwait(false);
            File.Move(temporary, CachePath(beta), overwrite: true);
        }
        catch (Exception exception)
        {
            CompanionLog.Write("themes.class_table_refresh", exception);
        }
        finally
        {
            lock (gate)
            {
                var channel = channels[beta];
                channels[beta] = (table ?? channel.Table, channel.CheckedUtc, null);
            }
        }
    }
}
