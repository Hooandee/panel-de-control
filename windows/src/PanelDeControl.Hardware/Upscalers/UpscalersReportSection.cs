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
        var report = install.Engine == "optiscaler" ? OptiScalerLog.Read(install.Target, UpscalerVerdict.Since(stored.InstalledAt)) : null;
        var helixFacts = install.Engine == "helixsr" ? HelixLog.ReadInstall(install, stored.InstalledAt) : null;
        var provider = report is null ? null : OptiScalerLog.ProviderObservationOf(report);
        var fallback = report is null ? null : OptiScalerLog.FallbackOf(install.Engine, install.Build, report);
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
            ["ini"] = install.Engine == "optiscaler" ? Ini(install) : null,
            ["last_error"] = lastError,
            ["log"] = new JsonObject
            {
                ["present"] = log.Present,
                ["modified"] = log.Modified is { } modified ? modified.ToString("O", CultureInfo.InvariantCulture) : null,
                ["upscaler_created"] = log.UpscalerCreated,
                ["verdict"] = report is not null ? OptiScalerLog.Verdict(report) : helixFacts is not null ? HelixLog.Verdict(helixFacts) : null,
                ["stale"] = report?.Stale ?? helixFacts?.Stale,
                ["version"] = report?.Version,
                ["upscaler"] = report?.Upscaler ?? helixFacts?.Upscaler,
                ["input"] = report?.Input,
                ["fg"] = report?.FrameGeneration,
                ["fg_state"] = report?.FrameGenerationState,
                ["fsr4_model"] = report?.Fsr4Model,
                ["provider_name"] = provider?.Name,
                ["provider_version"] = provider?.Version,
                ["provider_confidence"] = provider?.Confidence,
                ["fallback"] = fallback is null ? null : new JsonObject { ["requested"] = fallback.Requested, ["observed"] = fallback.Observed, ["reason"] = fallback.Reason },
                ["texture_failure"] = report?.TextureFailure,
                ["errors"] = report?.Errors,
            },
        };
    }

    /// <summary>OptiScaler.ini as it stands, against what Panel last wrote and the keys the user edited by hand.</summary>
    private static JsonObject Ini(InstalledUpscaler install)
    {
        var text = IniDiagnostics.ReadText(install.Target);
        var drift = IniDiagnostics.Drift(install, text, IniDiagnostics.ModifiedAt(install.Target));
        var values = new JsonObject();
        foreach (var pair in IniDiagnostics.Values(text))
        {
            values[pair.Key] = pair.Value;
        }

        var changed = new JsonObject();
        foreach (var change in drift.Keys)
        {
            changed[change.Key] = change.ValueOmitted
                ? new JsonObject { ["value_omitted"] = true }
                : new JsonObject { ["panel"] = change.Panel, ["now"] = change.Now };
        }

        var advanced = new JsonArray();
        foreach (var pair in install.Edited.Take(IniDiagnostics.MaximumAdvanced))
        {
            var request = IniDiagnostics.Request(text, pair.Key, pair.Value);
            advanced.Add(request.Value is null
                ? new JsonObject { ["key"] = request.Key, ["value_omitted"] = true }
                : new JsonObject { ["key"] = request.Key, ["value"] = request.Value });
        }

        return new JsonObject
        {
            ["missing"] = text is null ? true : null,
            ["values"] = values,
            ["drift"] = new JsonObject
            {
                ["status"] = drift.Status,
                ["written_at"] = drift.WrittenAt,
                ["modified_at"] = drift.ModifiedAt,
                ["keys"] = changed,
            },
            ["advanced"] = advanced,
        };
    }

    private static JsonArray Names(IEnumerable<string> relative) =>
        new(relative.Take(MaximumNames).Select(name => (JsonNode?)JsonValue.Create("<game>/" + name)).ToArray());
}
