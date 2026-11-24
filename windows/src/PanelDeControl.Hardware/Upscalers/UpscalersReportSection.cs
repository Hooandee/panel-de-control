using System.Globalization;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>
/// The <c>upscalers</c> section of a report: what Panel remembers per game, what the game's manifest says, and the
/// last operations. Whatever is not read is null; game folders appear only as <c>&lt;game&gt;/relative</c>.
/// </summary>
public static class UpscalersReportSection
{
    public const int MaximumGames = 12;
    public const int MaximumJournal = 20;
    public const int MaximumNames = 20;

    public static JsonObject Build(UpscalerStateStore store, GpuFamilyResult? gpu, int? catalogVersion)
    {
        var games = new JsonArray();
        var installed = store.InstalledAppIds
            .Select(appId => (AppId: appId, Stored: store.Install(appId)!))
            .OrderByDescending(item => item.Stored.InstalledAt)
            .Take(MaximumGames);
        foreach (var (appId, stored) in installed)
        {
            games.Add(Game(store, appId, stored));
        }

        var journal = new JsonArray();
        foreach (var action in store.RecentActions(MaximumJournal))
        {
            journal.Add(new JsonObject
            {
                ["at"] = action.At,
                ["appid"] = action.AppId,
                ["action"] = action.Action,
                ["state"] = action.State,
                ["build"] = action.Build,
                ["error"] = action.Error,
            });
        }

        return new JsonObject
        {
            ["gpu"] = gpu is null ? null : new JsonObject { ["family"] = gpu.Generation, ["source"] = gpu.Source },
            ["catalog_version"] = catalogVersion,
            ["games"] = games,
            ["journal"] = journal,
        };
    }

    private static JsonObject Game(UpscalerStateStore store, string appId, StoredUpscaler stored)
    {
        var install = stored.Install;
        var manifest = ManifestCheck.Verify(install.Target);
        var log = OptiScalerLogFacts.Read(install.Target);
        var lastError = store.Actions(appId).LastOrDefault(action => action.Error is not null)?.Error;
        return new JsonObject
        {
            ["appid"] = appId,
            ["build"] = install.Build,
            ["engine"] = install.Engine,
            ["proxy"] = install.Proxy,
            ["installed_at"] = stored.InstalledAt,
            ["manifest"] = new JsonObject
            {
                ["present"] = manifest.Present,
                ["complete"] = manifest.Present ? manifest.Complete : null,
                ["files"] = manifest.Present ? manifest.Files : null,
                ["ok"] = manifest.Present ? manifest.Files - manifest.Missing.Count - manifest.Changed.Count : null,
                ["changed"] = manifest.Present ? manifest.Changed.Count : null,
                ["missing"] = manifest.Present ? manifest.Missing.Count : null,
                ["changed_files"] = manifest.Present ? Names(manifest.Changed) : null,
                ["missing_files"] = manifest.Present ? Names(manifest.Missing) : null,
            },
            ["last_error"] = lastError,
            ["log"] = new JsonObject
            {
                ["present"] = log.Present,
                ["modified"] = log.Modified is { } modified ? modified.ToString("O", CultureInfo.InvariantCulture) : null,
                ["upscaler_created"] = log.UpscalerCreated,
            },
        };
    }

    private static JsonArray Names(IEnumerable<string> relative) =>
        new(relative.Take(MaximumNames).Select(name => (JsonNode?)JsonValue.Create("<game>/" + name)).ToArray());
}
