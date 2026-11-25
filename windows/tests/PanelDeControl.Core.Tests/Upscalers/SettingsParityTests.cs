using System.Globalization;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// The INI schema, image controls, hand-edit resolution and configure overrides must give the Linux backend's answers for
/// every case of settings_parity.json (written by tests/test_upscalers_settings_parity.py).
/// </summary>
public sealed class SettingsParityTests
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "settings_parity.json")))!.AsObject();
    private static readonly BuildCatalog Catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));

    [Fact]
    public void SchemaMatches()
    {
        var schema = Fixture["schema"]!.AsObject();
        var managed = new HashSet<string>(schema["managed"]!.AsArray().Select(item => item!.GetValue<string>()), StringComparer.Ordinal);
        Same(schema["expected"], SchemaJson(IniText.Schema(schema["text"]!.GetValue<string>(), managed)), "lf");
        Same(schema["crlf_expected"], SchemaJson(IniText.Schema(schema["crlf_text"]!.GetValue<string>(), managed)), "crlf");
        Same(schema["no_managed_expected"], SchemaJson(IniText.Schema(schema["text"]!.GetValue<string>())), "no managed");
        Same(schema["empty_expected"], SchemaJson(IniText.Schema("")), "empty");
        Same(schema["no_sections_expected"], SchemaJson(IniText.Schema("Key=1\n; help\n")), "no sections");
    }

    [Fact]
    public void ImageValuesMatch()
    {
        var cases = Fixture["image_values"]!.AsArray();
        Assert.True(cases.Count > 30);
        foreach (var item in cases)
        {
            var name = item!["name"]!.GetValue<string>();
            var actual = Attempt(() =>
            {
                var result = new JsonObject();
                foreach (var pair in ImageSettings.Values(item["text"]!.GetValue<string>()))
                {
                    result[pair.Key] = pair.Value;
                }
                return result;
            });
            Same(item["expected"], actual, name);
        }
    }

    [Fact]
    public void ImageStateMatches()
    {
        var cases = Fixture["image_state"]!.AsArray();
        Assert.True(cases.Count > 100);
        foreach (var item in cases)
        {
            var actual = Attempt(() =>
            {
                var state = ImageSettings.State(item!["text"]!.GetValue<string>(), item["helix"]!.GetValue<bool>(), item["managed"]!.GetValue<bool>());
                return StateJson(state);
            });
            Same(item!["expected"], actual, item["name"]!.GetValue<string>());
        }
    }

    [Fact]
    public void ImageChangesMatch()
    {
        var cases = Fixture["image_changes"]!.AsArray();
        Assert.True(cases.Count > 100);
        foreach (var item in cases)
        {
            var text = item!["text"]!.GetValue<string>();
            var request = Request(item["request"]!.AsObject());
            var actual = Attempt(() =>
            {
                var state = ImageSettings.State(text, item["helix"]!.GetValue<bool>(), false);
                return Pairs(ImageSettings.Changes(request, state, text));
            });
            Same(item["expected"], actual, item["name"]!.GetValue<string>());
        }
    }

    [Fact]
    public void ImageReceiptsMatch()
    {
        var cases = Fixture["image_receipt"]!.AsArray();
        Assert.True(cases.Count > 20);
        foreach (var item in cases)
        {
            var name = item!["name"]!.GetValue<string>();
            var helix = item["helix"]!.GetValue<bool>();
            var target = item["target"]!.GetValue<string>();
            var text = item["text"]!.GetValue<string>();
            ImageSettingsReceipt? receipt = null;
            var steps = item["steps"]!.AsArray();
            var results = item["results"]!.AsArray();
            for (var index = 0; index < steps.Count; index++)
            {
                var step = steps[index]!.AsObject();
                var expected = results[index]!.AsObject();
                JsonNode? changes = null;
                switch (step["op"]!.GetValue<string>())
                {
                    case "set":
                        var list = ImageSettings.Changes(Request(step["request"]!.AsObject()), ImageSettings.State(text, helix, false), text);
                        receipt = ImageSettings.Receipt(receipt, target, text, list);
                        text = IniText.Apply(text, list);
                        changes = Pairs(list);
                        break;
                    case "restore":
                        text = ImageSettings.Restored(text, receipt!);
                        receipt = null;
                        break;
                    case "edit":
                        text = IniText.Apply(text, step["values"]!.AsObject().Select(pair => new KeyValuePair<string, string>(pair.Key, pair.Value!.GetValue<string>())));
                        break;
                }

                var label = $"{name} step {index}";
                Assert.Equal(expected["text"]!.GetValue<string>(), text);
                Same(expected["receipt"], receipt is null ? null : new JsonObject
                {
                    ["target"] = receipt.Target,
                    ["original"] = Pairs(receipt.Original),
                    ["applied"] = Pairs(receipt.Applied),
                }, label);
                if (changes is not null)
                {
                    Same(expected["changes"], changes, label);
                }
            }
        }
    }

    [Fact]
    public void Fixed2Matches()
    {
        foreach (var item in Fixture["fixed2"]!.AsArray())
        {
            var number = item!["number"]!.GetValue<double>();
            Assert.Equal(item["expected"]!.GetValue<string>(), ImageSettings.Fixed2(number));
        }
    }

    [Fact]
    public void ResolveSettingsMatches()
    {
        var schema = IniText.Schema(Fixture["schema"]!["text"]!.GetValue<string>());
        var cases = Fixture["resolve_settings"]!.AsArray();
        Assert.True(cases.Count >= 10);
        foreach (var item in cases)
        {
            var settings = item!["settings"]!.AsArray().Select(pair => new KeyValuePair<string, string>(pair![0]!.GetValue<string>(), pair[1]!.GetValue<string>()));
            Same(item["expected"], Pairs(UpscalerSettings.ResolveSettings(schema, settings)), item["name"]!.GetValue<string>());
        }
    }

    [Fact]
    public void ConfigureOverridesMatch()
    {
        var cases = Fixture["configure"]!.AsArray();
        Assert.True(cases.Count >= 10);
        foreach (var item in cases)
        {
            var name = item!["name"]!.GetValue<string>();
            var choiceJson = item["choice"]!.AsObject();
            var choice = new UpscalerChoice
            {
                Quality = choiceJson["quality"]?.GetValue<string>(),
                Sharpness = choiceJson["sharpness"]?.GetValue<string>(),
                FrameGen = choiceJson["fg"]?.GetValue<string>() == "on",
                FrameGenRoute = choiceJson["fg_route"]?.GetValue<string>(),
                Model = choiceJson["model"]?.GetValue<string>(),
            };
            var install = new InstalledUpscaler
            {
                Build = item["build"]!.GetValue<string>(),
                Anr = item["anr"]!.GetValue<bool>(),
                ImageOverrides = item["image_overrides"] is JsonObject image
                    ? image.Select(pair => new KeyValuePair<string, string>(pair.Key, pair.Value!.GetValue<string>())).ToList()
                    : new List<KeyValuePair<string, string>>(),
            };
            var text = item["text"]!.GetValue<string>();
            var plan = item["plan"] is JsonObject route
                ? new FrameGenPlan("game", new[]
                {
                    new KeyValuePair<string, FrameGenRoute>("game", new FrameGenRoute(route["input"]!.GetValue<string>(), route["output"]!.GetValue<string>(),
                        route["follows_game"]!.GetValue<bool>(), "game", false, route["provider"]?.GetValue<string>())),
                })
                : null;
            Same(item["configure"], Pairs(UpscalerSettings.ConfigureOverrides(Catalog, install, choice, plan, text)), name + " configure");
            Same(item["running"], Pairs(UpscalerSettings.RunningOverrides(Catalog, install, choice, text)), name + " running");
            Same(item["options_only"], Pairs(PanelIni.OptionOverrides(Catalog, choice)), name + " options");
            Same(item["fg_off"], Pairs(UpscalerSettings.FrameGenOff(install)), name + " fg off");
        }
    }

    [Fact]
    public void ManagedKeysMatch()
    {
        foreach (var item in Fixture["managed_keys"]!.AsArray())
        {
            var install = new InstalledUpscaler
            {
                Build = item!["install"]!["build"]?.GetValue<string>() ?? "",
                Managed = item["install"]!["managed"]?.AsArray().Select(key => key!.GetValue<string>()).ToList() ?? new List<string>(),
            };
            var actual = UpscalerSettings.ManagedKeys(Catalog, install).OrderBy(key => key, StringComparer.Ordinal).ToList();
            Assert.Equal(item["expected"]!.AsArray().Select(key => key!.GetValue<string>()), actual);
        }
    }

    private static ImageSettingsRequest Request(JsonObject json)
    {
        var request = new ImageSettingsRequest { Int8 = json["int8"]?.GetValue<string>() };
        if (json["sharpness"] is JsonObject sharpness)
        {
            request.Sharpness = new ImageSharpness
            {
                Enabled = sharpness["enabled"]?.GetValue<bool>(),
                Value = sharpness["value"]?.GetValue<double>(),
            };
        }
        return request;
    }

    private static JsonNode Attempt(Func<JsonNode> run)
    {
        try
        {
            return run();
        }
        catch (ImageSettingsException error)
        {
            return new JsonObject { ["error"] = error.Code };
        }
    }

    private static JsonArray Pairs(IEnumerable<KeyValuePair<string, string>> pairs)
    {
        var result = new JsonArray();
        foreach (var pair in pairs)
        {
            result.Add(new JsonArray(JsonValue.Create(pair.Key), JsonValue.Create(pair.Value)));
        }
        return result;
    }

    private static JsonObject StateJson(ImageSettingsState state)
    {
        var result = new JsonObject
        {
            ["supported"] = state.Supported,
            ["sharpness"] = state.Sharpness is null ? null : new JsonObject { ["enabled"] = state.Sharpness.Enabled, ["value"] = state.Sharpness.Value },
            ["int8"] = state.Int8,
            ["managed"] = state.Managed,
        };
        if (state.Reason is not null)
        {
            result["reason"] = state.Reason;
        }
        return result;
    }

    private static JsonArray SchemaJson(IReadOnlyList<IniSchemaSection> schema) =>
        new(schema.Select(section => (JsonNode?)new JsonObject
        {
            ["name"] = section.Name,
            ["keys"] = new JsonArray(section.Keys.Select(key => (JsonNode?)new JsonObject
            {
                ["key"] = key.Key,
                ["value"] = key.Value,
                ["help"] = new JsonArray(key.Help.Select(line => (JsonNode?)JsonValue.Create(line)).ToArray()),
                ["choices"] = key.Choices is null ? null : new JsonArray(key.Choices.Select(choice => (JsonNode?)JsonValue.Create(choice)).ToArray()),
                ["default"] = key.Default,
                ["managed"] = key.Managed,
            }).ToArray()),
        }).ToArray());

    private static void Same(JsonNode? expected, JsonNode? actual, string label) => Assert.True(Canonical(expected) == Canonical(actual), $"{label}\nexpected {Canonical(expected)}\nactual   {Canonical(actual)}");

    private static string Canonical(JsonNode? node) => node switch
    {
        null => "null",
        JsonObject item => "{" + string.Join(",", item.Select(pair => $"\"{pair.Key}\":{Canonical(pair.Value)}")) + "}",
        JsonArray list => "[" + string.Join(",", list.Select(Canonical)) + "]",
        JsonValue value when value.TryGetValue<double>(out var number) && value.GetValueKind() == System.Text.Json.JsonValueKind.Number
            => number.ToString("R", CultureInfo.InvariantCulture),
        _ => node.ToJsonString(),
    };
}
