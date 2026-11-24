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
public sealed class UpscalerStateStore
{
    public const int ActionLimit = 20;
    public const long MaximumBytes = 4 * 1024 * 1024;

    private static readonly UTF8Encoding Utf8 = new(false);
    private readonly object _lock = new();
    private readonly string _path;
    private readonly Action<string, string> _replace;
    private readonly Dictionary<string, StoredUpscaler> _installs = new(StringComparer.Ordinal);
    private readonly Dictionary<string, List<UpscalerAction>> _actions = new(StringComparer.Ordinal);

    /// <param name="path">The state file.</param>
    /// <param name="replace">Moves the finished temporary file over the state file; replaceable so a test can fail it.</param>
    public UpscalerStateStore(string path, Action<string, string>? replace = null)
    {
        _path = path;
        _replace = replace ?? DefaultReplace;
        Load();
    }

    public string FilePath => _path;

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

    public StoredUpscaler? Install(string appId)
    {
        lock (_lock)
        {
            return _installs.TryGetValue(appId, out var stored) ? stored : null;
        }
    }

    public IReadOnlyList<UpscalerAction> Actions(string appId)
    {
        lock (_lock)
        {
            return _actions.TryGetValue(appId, out var list) ? list.ToList() : new List<UpscalerAction>();
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
            Mutate(() => _installs[appId] = new StoredUpscaler(install, installedAt));
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
        try
        {
            change();
            Save();
        }
        catch
        {
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
        }
    }

    private void Save()
    {
        var games = new List<KeyValuePair<string, DataValue>>();
        foreach (var appId in _installs.Keys.Concat(_actions.Keys).Distinct(StringComparer.Ordinal).OrderBy(key => key, StringComparer.Ordinal))
        {
            var members = new List<KeyValuePair<string, DataValue>>();
            if (_installs.TryGetValue(appId, out var stored))
            {
                members.Add(Member("install", WriteInstall(stored)));
            }

            members.Add(Member("actions", new DataArray(
                (_actions.TryGetValue(appId, out var list) ? list : new List<UpscalerAction>()).Select(WriteAction).ToList())));
            games.Add(Member(appId, new DataObject(members)));
        }

        var text = PythonJson.Write(new DataObject(new[] { Member("games", new DataObject(games)) }));
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
            Managed = managed,
            Components = components,
        };
        var at = install.Get("installed_at") is DataNumber number ? number.Real : 0;
        return new StoredUpscaler(installed, at);
    }

    internal static DataValue WriteInstall(StoredUpscaler stored)
    {
        var install = stored.Install;
        var options = install.Options;
        return new DataObject(new[]
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
        });
    }

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

    private static DataValue Optional(string? value) => value is null ? DataNull.Instance : new DataString(value);

    private static string? Text(DataValue? value) => (value as DataString)?.Value;
}
