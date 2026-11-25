using System.Text;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>An install as Panel remembers it; the game's own manifest decides whether it is still there.</summary>
public sealed class StoredUpscaler
{
    public StoredUpscaler(InstalledUpscaler install, double installedAt)
    {
        Install = install;
        InstalledAt = installedAt;
    }

    public InstalledUpscaler Install { get; }

    /// <summary>Unix seconds.</summary>
    public double InstalledAt { get; }
}

/// <summary>One entry of the operations journal.</summary>
public sealed class UpscalerAction
{
    public UpscalerAction(double at, string appId, string action, string state, string? build = null, string? error = null)
    {
        At = at;
        AppId = appId;
        Action = action;
        State = state;
        Build = build;
        Error = error;
    }

    public double At { get; }

    public string AppId { get; }

    public string Action { get; }

    public string State { get; }

    public string? Build { get; }

    public string? Error { get; }
}

/// <summary>
/// <c>state.json</c> with the Linux layout (<c>games.&lt;appid&gt;.install</c>, <c>games.&lt;appid&gt;.actions</c>), written
/// through a temporary file so a crash never leaves half a file.
/// </summary>
/// <summary>One install in a game's history, as Linux keeps it: <c>result</c> starts pending and the log settles it.</summary>
public sealed class UpscalerHistoryItem
{
    public UpscalerHistoryItem(double at, string build, string? proxy, string result, string? exe, string? model = null, string? observed = null)
    {
        At = at;
        Build = build;
        Proxy = proxy;
        Result = result;
        Exe = exe;
        Model = model;
        Observed = observed;
    }

    public double At { get; }

    public string Build { get; }

    public string? Proxy { get; }

    public string Result { get; }

    public string? Exe { get; }

    public string? Model { get; }

    public string? Observed { get; }
}

public sealed class UpscalerStateStore
{
    public const int ActionLimit = 20;
    public const int HistoryLimit = 20;
    public const long MaximumBytes = 4 * 1024 * 1024;

    private static readonly UTF8Encoding Utf8 = new(false);
    private readonly object _lock = new();
    private readonly string _path;
    private readonly Action<string, string> _replace;
    private readonly Dictionary<string, StoredUpscaler> _installs = new(StringComparer.Ordinal);
    private readonly Dictionary<string, List<UpscalerAction>> _actions = new(StringComparer.Ordinal);
    private readonly Dictionary<string, List<UpscalerHistoryItem>> _history = new(StringComparer.Ordinal);
    private readonly Dictionary<string, List<string>> _strandedArgs = new(StringComparer.Ordinal);
    private string? _inGameMode;
    private readonly Dictionary<string, ImageSettingsReceipt> _imageReceipts = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _exes = new(StringComparer.Ordinal);
    private readonly Dictionary<string, ForeignBackup> _foreignBackups = new(StringComparer.Ordinal);

    /// <param name="path">The state file.</param>
    /// <param name="replace">Moves the finished temporary file over the state file; replaceable so a test can fail it.</param>
    public UpscalerStateStore(string path, Action<string, string>? replace = null)
    {
        _path = path;
        _replace = replace ?? DefaultReplace;
        Load();
    }

    public string FilePath => _path;

    /// <summary>The in-game badge's mode: the stored one, else <see cref="InGameModes.Default"/>.</summary>
    public string InGameMode
    {
        get
        {
            lock (_lock)
            {
                return InGameModes.Normalize(_inGameMode);
            }
        }
    }

    public void SetInGameMode(string mode)
    {
        lock (_lock)
        {
            Mutate(() => _inGameMode = mode);
        }
    }

    public IReadOnlyList<string> InstalledAppIds
    {
        get
        {
            lock (_lock)
            {
                return _installs.Keys.OrderBy(key => key, StringComparer.Ordinal).ToList();
            }
        }
    }

    /// <summary>A copy: changing it never changes what the store holds until <see cref="SetInstall"/> saves it.</summary>
    public StoredUpscaler? Install(string appId)
    {
        lock (_lock)
        {
            return _installs.TryGetValue(appId, out var stored) ? Copy(stored) : null;
        }
    }

    /// <summary>The executable the user chose for this game, relative to its folder with '/' separators; null when none.</summary>
    public string? Exe(string appId)
    {
        lock (_lock)
        {
            return _exes.TryGetValue(appId, out var exe) ? exe : null;
        }
    }

    public void SetExe(string appId, string? exe)
    {
        lock (_lock)
        {
            Mutate(() =>
            {
                if (string.IsNullOrEmpty(exe))
                {
                    _exes.Remove(appId);
                }
                else
                {
                    _exes[appId] = exe!;
                }
            });
        }
    }

    /// <summary>Another tool's files Panel moved aside for this game; a copy.</summary>
    public ForeignBackup? ForeignBackupOf(string appId)
    {
        lock (_lock)
        {
            return _foreignBackups.TryGetValue(appId, out var backup) ? backup.Copy() : null;
        }
    }

    public void SetForeignBackup(string appId, ForeignBackup? backup)
    {
        lock (_lock)
        {
            Mutate(() =>
            {
                if (backup is null)
                {
                    _foreignBackups.Remove(appId);
                }
                else
                {
                    _foreignBackups[appId] = backup.Copy();
                }
            });
        }
    }

    /// <summary>Launch arguments Panel added and could not take out of Steam yet (Steam closed or without its debugging port).</summary>
    public IReadOnlyList<string> StrandedArgs(string appId)
    {
        lock (_lock)
        {
            return _strandedArgs.TryGetValue(appId, out var list) ? list.ToList() : new List<string>();
        }
    }

    public IReadOnlyList<string> AppsWithStrandedArgs
    {
        get
        {
            lock (_lock)
            {
                return _strandedArgs.Keys.ToList();
            }
        }
    }

    public void SetStrandedArgs(string appId, IReadOnlyList<string> args)
    {
        lock (_lock)
        {
            Mutate(() =>
            {
                if (args.Count == 0)
                {
                    _strandedArgs.Remove(appId);
                }
                else
                {
                    _strandedArgs[appId] = args.Distinct(StringComparer.Ordinal).ToList();
                }
            });
        }
    }

    /// <summary>What the image controls changed in this game's OptiScaler.ini and the values they replaced.</summary>
    public ImageSettingsReceipt? ImageReceipt(string appId)
    {
        lock (_lock)
        {
            return _imageReceipts.TryGetValue(appId, out var receipt) ? receipt.Copy() : null;
        }
    }

    /// <summary>Saves the receipt and, when given, the install in one write; a null receipt drops it.</summary>
    public void SetImageReceipt(string appId, ImageSettingsReceipt? receipt, StoredUpscaler? install = null)
    {
        lock (_lock)
        {
            Mutate(() =>
            {
                if (receipt is null)
                {
                    _imageReceipts.Remove(appId);
                }
                else
                {
                    _imageReceipts[appId] = receipt.Copy();
                }

                if (install is not null)
                {
                    _installs[appId] = Copy(install);
                }
            });
        }
    }

    public IReadOnlyList<UpscalerAction> Actions(string appId)
    {
        lock (_lock)
        {
            return _actions.TryGetValue(appId, out var list) ? list.ToList() : new List<UpscalerAction>();
        }
    }

    public IReadOnlyList<UpscalerHistoryItem> History(string appId)
    {
        lock (_lock)
        {
            return _history.TryGetValue(appId, out var list) ? list.ToList() : new List<UpscalerHistoryItem>();
        }
    }

    public void AddHistory(string appId, UpscalerHistoryItem item)
    {
        lock (_lock)
        {
            Mutate(() =>
            {
                if (!_history.TryGetValue(appId, out var list))
                {
                    list = new List<UpscalerHistoryItem>();
                    _history[appId] = list;
                }

                list.Add(item);
                if (list.Count > HistoryLimit)
                {
                    list.RemoveRange(0, list.Count - HistoryLimit);
                }
            });
        }
    }

    /// <summary>Settles the newest entry once the log has spoken, only while it is still the install in the game.</summary>
    public bool SettleHistory(string appId, string build, string result, string? observed)
    {
        lock (_lock)
        {
            if (!_history.TryGetValue(appId, out var list) || list.Count == 0)
            {
                return false;
            }

            var last = list[list.Count - 1];
            if (last.Build != build || (last.Result == result && last.Observed == observed))
            {
                return false;
            }

            Mutate(() => list[list.Count - 1] = new UpscalerHistoryItem(last.At, last.Build, last.Proxy, result, last.Exe, last.Model, observed));
            return true;
        }
    }

    /// <summary>The newest operations of every game, oldest first.</summary>
    public IReadOnlyList<UpscalerAction> RecentActions(int limit)
    {
        lock (_lock)
        {
            return _actions.Values.SelectMany(list => list).OrderBy(action => action.At).ThenBy(action => action.AppId, StringComparer.Ordinal)
                .Reverse().Take(limit).Reverse().ToList();
        }
    }

    public void SetInstall(string appId, InstalledUpscaler install, double installedAt)
    {
        lock (_lock)
        {
            Mutate(() => _installs[appId] = Copy(new StoredUpscaler(install, installedAt)));
        }
    }

    public void ClearInstall(string appId)
    {
        lock (_lock)
        {
            Mutate(() => _installs.Remove(appId));
        }
    }

    public void Record(UpscalerAction action)
    {
        lock (_lock)
        {
            Mutate(() =>
            {
                if (!_actions.TryGetValue(action.AppId, out var list))
                {
                    list = new List<UpscalerAction>();
                    _actions[action.AppId] = list;
                }

                list.Add(action);
                if (list.Count > ActionLimit)
                {
                    list.RemoveRange(0, list.Count - ActionLimit);
                }
            });
        }
    }

    // A failed write puts memory back as it was, so what is reported is what the file says.
    private void Mutate(Action change)
    {
        var installs = new Dictionary<string, StoredUpscaler>(_installs, StringComparer.Ordinal);
        var actions = _actions.ToDictionary(pair => pair.Key, pair => pair.Value.ToList(), StringComparer.Ordinal);
        var history = _history.ToDictionary(pair => pair.Key, pair => pair.Value.ToList(), StringComparer.Ordinal);
        var stranded = _strandedArgs.ToDictionary(pair => pair.Key, pair => pair.Value.ToList(), StringComparer.Ordinal);
        var inGameMode = _inGameMode;
        var receipts = new Dictionary<string, ImageSettingsReceipt>(_imageReceipts, StringComparer.Ordinal);
        var exes = new Dictionary<string, string>(_exes, StringComparer.Ordinal);
        var foreign = _foreignBackups.ToDictionary(pair => pair.Key, pair => pair.Value.Copy(), StringComparer.Ordinal);
        try
        {
            change();
            Save();
        }
        catch
        {
            _inGameMode = inGameMode;
            _installs.Clear();
            foreach (var pair in installs)
            {
                _installs[pair.Key] = pair.Value;
            }

            _actions.Clear();
            foreach (var pair in actions)
            {
                _actions[pair.Key] = pair.Value;
            }

            _history.Clear();
            foreach (var pair in history)
            {
                _history[pair.Key] = pair.Value;
            }

            _strandedArgs.Clear();
            foreach (var pair in stranded)
            {
                _strandedArgs[pair.Key] = pair.Value;
            }

            _imageReceipts.Clear();
            foreach (var pair in receipts)
            {
                _imageReceipts[pair.Key] = pair.Value;
            }

            _exes.Clear();
            foreach (var pair in exes)
            {
                _exes[pair.Key] = pair.Value;
            }

            _foreignBackups.Clear();
            foreach (var pair in foreign)
            {
                _foreignBackups[pair.Key] = pair.Value;
            }

            throw;
        }
    }

    private void Load()
    {
        try
        {
            var info = new FileInfo(_path);
            if (!info.Exists || info.Length > MaximumBytes)
            {
                return;
            }

            if (DataValue.Parse(File.ReadAllText(_path, Utf8)) is not DataObject document || document.Get("games") is not DataObject games)
            {
                return;
            }

            if (document.Get("settings") is DataObject settings && settings.Get("ingame") is DataString mode && InGameModes.IsValid(mode.Value))
            {
                _inGameMode = mode.Value;
            }

            foreach (var game in games.Members)
            {
                if (game.Value is not DataObject entry)
                {
                    continue;
                }

                if (entry.Get("install") is DataObject install && ReadInstall(install) is { } stored)
                {
                    _installs[game.Key] = stored;
                }

                if (entry.Get("stranded_args") is DataArray strandedArgs && DataValue.StringItems(strandedArgs) is { Count: > 0 } args)
                {
                    _strandedArgs[game.Key] = args.ToList();
                }

                if (entry.Get("exe") is DataString { Value.Length: > 0 } chosen)
                {
                    _exes[game.Key] = chosen.Value;
                }

                if (ForeignBackup.FromData(entry.Get("foreign_backup")) is { } foreignBackup)
                {
                    _foreignBackups[game.Key] = foreignBackup;
                }

                if (ReadReceipt(entry.Get("image_settings")) is { } receipt)
                {
                    _imageReceipts[game.Key] = receipt;
                }

                if (entry.Get("history") is DataArray past)
                {
                    var items = past.Items.OfType<DataObject>().Select(ReadHistory).Where(item => item is not null).Cast<UpscalerHistoryItem>().ToList();
                    if (items.Count > 0)
                    {
                        _history[game.Key] = items.Skip(Math.Max(0, items.Count - HistoryLimit)).ToList();
                    }
                }

                if (entry.Get("actions") is DataArray actions)
                {
                    var list = actions.Items.OfType<DataObject>().Select(item => ReadAction(game.Key, item)).Where(item => item is not null)
                        .Cast<UpscalerAction>().ToList();
                    if (list.Count > 0)
                    {
                        _actions[game.Key] = list.Skip(Math.Max(0, list.Count - ActionLimit)).ToList();
                    }
                }
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DataFormatException)
        {
            _installs.Clear();
            _actions.Clear();
            _history.Clear();
            _strandedArgs.Clear();
            _imageReceipts.Clear();
            _exes.Clear();
            _foreignBackups.Clear();
        }
    }

    private void Save()
    {
        var games = new List<KeyValuePair<string, DataValue>>();
        foreach (var appId in _installs.Keys.Concat(_actions.Keys).Concat(_history.Keys).Concat(_strandedArgs.Keys).Concat(_imageReceipts.Keys).Concat(_exes.Keys).Concat(_foreignBackups.Keys).Distinct(StringComparer.Ordinal).OrderBy(key => key, StringComparer.Ordinal))
        {
            var members = new List<KeyValuePair<string, DataValue>>();
            if (_installs.TryGetValue(appId, out var stored))
            {
                members.Add(Member("install", WriteInstall(stored)));
            }

            if (_exes.TryGetValue(appId, out var chosenExe))
            {
                members.Add(Member("exe", new DataString(chosenExe)));
            }

            if (_foreignBackups.TryGetValue(appId, out var savedBackup))
            {
                members.Add(Member("foreign_backup", savedBackup.ToData()));
            }

            if (_strandedArgs.TryGetValue(appId, out var strandedArgs) && strandedArgs.Count > 0)
            {
                members.Add(Member("stranded_args", new DataArray(strandedArgs.Select(arg => (DataValue)new DataString(arg)).ToList())));
            }

            if (_imageReceipts.TryGetValue(appId, out var receipt))
            {
                members.Add(Member("image_settings", WriteReceipt(receipt)));
            }

            if (_history.TryGetValue(appId, out var past) && past.Count > 0)
            {
                members.Add(Member("history", new DataArray(past.Select(WriteHistory).ToList())));
            }

            members.Add(Member("actions", new DataArray(
                (_actions.TryGetValue(appId, out var list) ? list : new List<UpscalerAction>()).Select(WriteAction).ToList())));
            games.Add(Member(appId, new DataObject(members)));
        }

        var top = new List<KeyValuePair<string, DataValue>> { Member("games", new DataObject(games)) };
        if (_inGameMode is not null)
        {
            top.Add(Member("settings", new DataObject(new[] { Member("ingame", new DataString(_inGameMode)) })));
        }

        var text = PythonJson.Write(new DataObject(top));
        var directory = Path.GetDirectoryName(_path);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var temporary = _path + ".tmp";
        File.WriteAllText(temporary, text, Utf8);
        try
        {
            _replace(temporary, _path);
        }
        catch
        {
            TryDelete(temporary);
            throw;
        }
    }

    private static void DefaultReplace(string temporary, string destination)
    {
        if (File.Exists(destination))
        {
            File.Replace(temporary, destination, null);
        }
        else
        {
            File.Move(temporary, destination);
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }

    internal static StoredUpscaler? ReadInstall(DataObject install)
    {
        var build = Text(install.Get("build"));
        var target = Text(install.Get("target"));
        if (string.IsNullOrEmpty(build) || string.IsNullOrEmpty(target))
        {
            return null;
        }

        var options = install.Get("options") as DataObject;
        var components = new List<KeyValuePair<string, string>>();
        if (install.Get("components") is DataArray list)
        {
            foreach (var item in list.Items.OfType<DataObject>())
            {
                if (Text(item.Get("id")) is { Length: > 0 } id && Text(item.Get("sha256")) is { Length: > 0 } digest)
                {
                    components.Add(new KeyValuePair<string, string>(id, digest));
                }
            }
        }

        var managed = install.Get("managed") is DataArray keys
            ? keys.Items.OfType<DataString>().Select(item => item.Value).ToList()
            : new List<string>();
        var installed = new InstalledUpscaler
        {
            Build = build!,
            Archive = Text(install.Get("archive")) ?? "",
            Engine = Text(install.Get("engine")) ?? "optiscaler",
            Proxy = Text(install.Get("proxy")) ?? "",
            Target = target!,
            Exe = Text(install.Get("exe")),
            Options = new UpscalerChoice
            {
                Quality = Text(options?.Get("quality")),
                Sharpness = Text(options?.Get("sharpness")),
                FrameGen = Text(options?.Get("fg")) == "on",
                FrameGenRoute = Text(options?.Get("fg_route")),
                Model = Text(options?.Get("model")),
            },
            FrameGenRoute = Text(install.Get("fg_route")),
            DllTargets = install.Get("dll_targets") is DataArray targets
                ? targets.Items.OfType<DataString>().Select(item => item.Value).ToList()
                : new List<string>(),
            Anr = install.Get("anr") is DataBool { Value: true },
            Args = DataValue.StringItems(install.Get("args")),
            AddedArgs = DataValue.StringItems(install.Get("added_args")),
            Way = Text(install.Get("way")) ?? "",
            ExeFolder = Text(install.Get("exe_folder")) ?? "",
            Log = Text(install.Get("log")) ?? "",
            HelixFile = Text(install.Get("helix_file")) ?? "",
            Managed = managed,
            Components = components,
            GameConfig = install.Get("game_config") is DataArray settings
                ? settings.Items.OfType<DataObject>().Select(setting => new GameConfigRecord
                {
                    File = Text(setting.Get("file")) ?? "",
                    Tag = Text(setting.Get("tag")) ?? "",
                    Value = Text(setting.Get("value")) ?? "",
                    State = Text(setting.Get("state")) ?? "missing",
                    Before = Text(setting.Get("before")),
                    Path = Text(setting.Get("path")),
                }).ToList()
                : new List<GameConfigRecord>(),
            Edited = Pairs(install.Get("edited")),
            VerificationSince = install.Get("verification_since") is DataNumber since ? since.Real : null,
            ImageOverrides = Pairs(install.Get("image_overrides")),
            IniWritten = install.Get("ini_written") is DataObject written && written.Get("at") is DataNumber writtenAt && written.Get("values") is DataObject
                ? new IniWritten(writtenAt.Real, Pairs(written.Get("values")))
                : null,
            Mod = install.Get("mod") is DataObject mod && Text(mod.Get("filename")) is { } modFile && Text(mod.Get("id")) is { } modId
                ? new KeyValuePair<string, string>(modFile, modId)
                : null,
        };
        var at = install.Get("installed_at") is DataNumber number ? number.Real : 0;
        return new StoredUpscaler(installed, at);
    }

    private static StoredUpscaler Copy(StoredUpscaler stored) =>
        ReadInstall((DataObject)WriteInstall(stored)) ?? stored;

    internal static DataValue WriteInstall(StoredUpscaler stored)
    {
        var install = stored.Install;
        var options = install.Options;
        var members = new List<KeyValuePair<string, DataValue>>
        {
            Member("build", new DataString(install.Build)),
            Member("archive", new DataString(install.Archive)),
            Member("engine", new DataString(install.Engine)),
            Member("proxy", new DataString(install.Proxy)),
            Member("target", new DataString(install.Target)),
            Member("exe", Optional(install.Exe)),
            Member("installed_at", new DataNumber(null, stored.InstalledAt)),
            Member("options", new DataObject(new[]
            {
                Member("quality", Optional(options.Quality)),
                Member("sharpness", Optional(options.Sharpness)),
                Member("fg", new DataString(options.FrameGen ? "on" : "off")),
                Member("fg_route", Optional(options.FrameGenRoute)),
                Member("model", Optional(options.Model)),
            })),
            Member("components", new DataArray(install.Components.Select(pair => (DataValue)new DataObject(new[]
            {
                Member("id", new DataString(pair.Key)),
                Member("sha256", new DataString(pair.Value)),
            })).ToList())),
            Member("managed", new DataArray(install.Managed.Select(key => (DataValue)new DataString(key)).ToList())),
            Member("dll_targets", new DataArray(install.DllTargets.Select(path => (DataValue)new DataString(path)).ToList())),
            Member("anr", new DataBool(install.Anr)),
            Member("args", new DataArray(install.Args.Select(arg => (DataValue)new DataString(arg)).ToList())),
            Member("added_args", new DataArray(install.AddedArgs.Select(arg => (DataValue)new DataString(arg)).ToList())),
        };
        if (install.VerificationSince is { } verificationSince)
        {
            members.Add(Member("verification_since", new DataNumber(null, verificationSince)));
        }
        if (install.Edited.Count > 0)
        {
            members.Add(Member("edited", WritePairs(install.Edited)));
        }
        if (install.ImageOverrides.Count > 0)
        {
            members.Add(Member("image_overrides", WritePairs(install.ImageOverrides)));
        }
        if (install.IniWritten is { } iniWritten)
        {
            members.Add(Member("ini_written", new DataObject(new[]
            {
                Member("at", new DataNumber(null, iniWritten.At)),
                Member("values", WritePairs(iniWritten.Values)),
            })));
        }
        if (install.Mod is { } mod)
        {
            members.Add(Member("mod", new DataObject(new[]
            {
                Member("filename", new DataString(mod.Key)),
                Member("id", new DataString(mod.Value)),
            })));
        }
        if (install.Engine == "helixsr")
        {
            members.Add(Member("way", new DataString(install.Way)));
            members.Add(Member("exe_folder", new DataString(install.ExeFolder)));
            members.Add(Member("log", new DataString(install.Log)));
            members.Add(Member("helix_file", new DataString(install.HelixFile)));
        }
        if (install.GameConfig.Count > 0)
        {
            members.Add(Member("game_config", new DataArray(install.GameConfig.Select(setting =>
            {
                var entry = new List<KeyValuePair<string, DataValue>>
                {
                    Member("file", new DataString(setting.File)),
                    Member("tag", new DataString(setting.Tag)),
                    Member("value", new DataString(setting.Value)),
                    Member("state", new DataString(setting.State)),
                };
                if (setting.Before is not null)
                {
                    entry.Add(Member("before", new DataString(setting.Before)));
                }
                if (setting.Path is not null)
                {
                    entry.Add(Member("path", new DataString(setting.Path)));
                }
                return (DataValue)new DataObject(entry);
            }).ToList())));
        }
        return new DataObject(members);
    }

    private static UpscalerHistoryItem? ReadHistory(DataObject item)
    {
        var build = Text(item.Get("build"));
        if (string.IsNullOrEmpty(build))
        {
            return null;
        }

        return new UpscalerHistoryItem(item.Get("at") is DataNumber at ? at.Real : 0, build!, Text(item.Get("proxy")),
            Text(item.Get("result")) ?? "pending", Text(item.Get("exe")), Text(item.Get("model")), Text(item.Get("observed")));
    }

    private static DataValue WriteHistory(UpscalerHistoryItem item) => new DataObject(new[]
    {
        Member("build", new DataString(item.Build)),
        Member("proxy", Optional(item.Proxy)),
        Member("at", new DataNumber(null, item.At)),
        Member("result", new DataString(item.Result)),
        Member("exe", Optional(item.Exe)),
        Member("model", Optional(item.Model)),
        Member("observed", Optional(item.Observed)),
    });

    private static UpscalerAction? ReadAction(string appId, DataObject item)
    {
        var action = Text(item.Get("action"));
        var state = Text(item.Get("state"));
        if (action is null || state is null)
        {
            return null;
        }

        return new UpscalerAction(item.Get("at") is DataNumber at ? at.Real : 0, appId, action, state, Text(item.Get("build")), Text(item.Get("error")));
    }

    private static DataValue WriteAction(UpscalerAction action) => new DataObject(new[]
    {
        Member("at", new DataNumber(null, action.At)),
        Member("action", new DataString(action.Action)),
        Member("state", new DataString(action.State)),
        Member("build", Optional(action.Build)),
        Member("error", Optional(action.Error)),
    });

    private static KeyValuePair<string, DataValue> Member(string key, DataValue value) => new(key, value);

    private static List<KeyValuePair<string, string>> Pairs(DataValue? value) =>
        value is DataObject mapping
            ? mapping.Members.Where(pair => pair.Value is DataString).Select(pair => new KeyValuePair<string, string>(pair.Key, ((DataString)pair.Value).Value)).ToList()
            : new List<KeyValuePair<string, string>>();

    private static DataObject WritePairs(IEnumerable<KeyValuePair<string, string>> pairs) =>
        new(pairs.Select(pair => Member(pair.Key, new DataString(pair.Value))).ToList());

    internal static ImageSettingsReceipt? ReadReceipt(DataValue? value) =>
        value is DataObject receipt && Text(receipt.Get("target")) is { Length: > 0 } target
            ? new ImageSettingsReceipt { Target = target, Original = Pairs(receipt.Get("original")), Applied = Pairs(receipt.Get("applied")) }
            : null;

    internal static DataObject WriteReceipt(ImageSettingsReceipt receipt) => new(new[]
    {
        Member("target", new DataString(receipt.Target)),
        Member("original", WritePairs(receipt.Original)),
        Member("applied", WritePairs(receipt.Applied)),
    });

    private static DataValue Optional(string? value) => value is null ? DataNull.Instance : new DataString(value);

    private static string? Text(DataValue? value) => (value as DataString)?.Value;
}
