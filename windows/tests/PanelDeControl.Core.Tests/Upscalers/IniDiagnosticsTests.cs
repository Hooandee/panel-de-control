using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>The ini_values, ini_drift and ini_request answers of ini_diagnostics.json (written by tests/test_upscalers_diagnostics_parity.py).</summary>
public sealed class IniDiagnosticsTests : IDisposable
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "ini_diagnostics.json")))!.AsObject();
    private readonly string _folder = Path.Combine(Path.GetTempPath(), "pdc-ini-diagnostics-" + Guid.NewGuid().ToString("N"));

    public IniDiagnosticsTests() => Directory.CreateDirectory(_folder);

    public void Dispose() => Directory.Delete(_folder, true);

    [Fact]
    public void ValuesMatchTheLinuxReport()
    {
        foreach (var item in Fixture["values"]!.AsArray())
        {
            var extra = item!["extra"]!.AsArray().Select(key => key!.GetValue<string>()).ToList();
            var text = item["text"]?.GetValue<string>();
            var expected = item["expected"]!.AsObject();
            var actual = IniDiagnostics.Values(text, extra);
            if (expected["missing"] is not null)
            {
                Assert.Null(text);
                Assert.Empty(actual);
                continue;
            }

            Assert.Equal(
                expected["values"]!.AsArray().Select(pair => pair![0]!.GetValue<string>() + "=" + pair[1]!.GetValue<string>()),
                actual.Select(pair => pair.Key + "=" + pair.Value));
        }
    }

    [Fact]
    public void DriftMatchesTheLinuxReport()
    {
        foreach (var item in Fixture["drift"]!.AsArray())
        {
            var install = new InstalledUpscaler { Edited = item!["edited"]!.AsObject().Select(pair => new KeyValuePair<string, string>(pair.Key, pair.Value!.GetValue<string>())).ToList() };
            if (item["written"] is JsonObject written)
            {
                install.IniWritten = new IniWritten(
                    written["at"]!.GetValue<double>(),
                    written["values"]!.AsObject().Select(pair => new KeyValuePair<string, string>(pair.Key, pair.Value!.GetValue<string>())).ToList());
            }

            var drift = IniDiagnostics.Drift(install, item["text"]?.GetValue<string>(), null);

            var expected = item["expected"]!.AsObject();
            var id = item["id"]!.GetValue<string>();
            Assert.True(expected["status"]!.GetValue<string>() == drift.Status, id);
            Assert.Equal(expected["written_at"]?.GetValue<double>(), drift.WrittenAt);
            if (drift.Status is IniDrift.Changed or IniDrift.AsWritten)
            {
                Assert.Equal(
                    expected["keys"]!.AsArray().Select(key => string.Join("|", key![0]!.GetValue<string>(), key[1]!.GetValue<string>(), key[2]?.GetValue<string>())),
                    drift.Keys.Select(change => string.Join("|", change.Key, change.Panel, change.Now)));
            }
        }
    }

    [Fact]
    public void AnEditedValueShowsOnlyWhenItIsANumberASwitchOrOneOfTheKeysChoices()
    {
        var text = Fixture["ini"]!.GetValue<string>();
        foreach (var item in Fixture["requests"]!.AsArray())
        {
            var request = IniDiagnostics.Request(text, item!["key"]!.GetValue<string>(), item["value"]!.GetValue<string>());

            var expected = item["expected"]!.AsObject();
            Assert.Equal(expected["key"]!.GetValue<string>(), request.Key);
            Assert.Equal(expected["value"]?.GetValue<string>(), request.Value);
            Assert.Equal(expected["value_omitted"] is not null, request.Value is null);
        }
    }

    [Fact]
    public void WhatPanelWroteSurvivesTheStateFile()
    {
        var store = new UpscalerStateStore(Path.Combine(_folder, "state.json"));
        var install = new InstalledUpscaler
        {
            Build = "fsr-3.1",
            Target = Path.Combine(_folder, "game"),
            IniWritten = new IniWritten(12.5, new[] { new KeyValuePair<string, string>("Log.LogLevel", "2"), new KeyValuePair<string, string>("Tweaks.Scale", "1.5") }),
        };
        store.SetInstall("100", install, 5);

        var again = new UpscalerStateStore(Path.Combine(_folder, "state.json")).Install("100")!.Install.IniWritten!;

        Assert.Equal(12.5, again.At);
        Assert.Equal(new[] { "Log.LogLevel=2", "Tweaks.Scale=1.5" }, again.Values.Select(pair => pair.Key + "=" + pair.Value));
        store.SetInstall("200", new InstalledUpscaler { Build = "fsr-3.1", Target = Path.Combine(_folder, "other") }, 5);
        Assert.Null(new UpscalerStateStore(Path.Combine(_folder, "state.json")).Install("200")!.Install.IniWritten);
    }

    [Fact]
    public void TheDiagnoseAndCompatRequestsKeepTheirNumbersAndRefuseWhatDoesNotBelongToThem()
    {
        static UpscalersRequest Back(UpscalersRequest request) => UpscalersWireCodec.DeserializeRequest(UpscalersWireCodec.SerializeRequest(request));
        Assert.Equal((24, 25), ((int)UpscalersOperation.Diagnose, (int)UpscalersOperation.Compat));
        var diagnose = Back(UpscalersRequest.Diagnose("100"));
        Assert.Equal((UpscalersOperation.Diagnose, "100", null), (diagnose.Operation, diagnose.AppId, diagnose.Appids));
        Assert.Equal(new[] { "1", "22" }, Back(UpscalersRequest.Compat(new[] { "1", "22" })).Appids);
        var fullest = Enumerable.Range(1_000_000_000, UpscalersRequest.MaximumCompatAppids).Select(id => id.ToString()).ToArray();
        Assert.Equal(UpscalersRequest.MaximumCompatAppids, Back(UpscalersRequest.Compat(fullest)).Appids!.Length);
        Assert.True(UpscalersWireCodec.SerializeRequest(UpscalersRequest.Compat(fullest)).Length <= UpscalersWireCodec.MaximumRequestLength);

        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.Compat(Array.Empty<string>())));
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.Compat(new[] { "12a" })));
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.Compat(new[] { "12345678901" })));
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeRequest(UpscalersRequest.Compat(Enumerable.Range(1, UpscalersRequest.MaximumCompatAppids + 1).Select(id => id.ToString()).ToArray())));
        foreach (var payload in new[]
        {
            "{\"operation\":0,\"appids\":[\"1\"]}",
            "{\"operation\":1,\"appid\":\"1\",\"appids\":[\"1\"]}",
            "{\"operation\":19,\"appid\":\"1\",\"path\":\"C:\\\\a.zip\",\"appids\":[\"1\"]}",
            "{\"operation\":21,\"dependency\":\"x\",\"appids\":[\"1\"]}",
            "{\"operation\":24,\"appid\":\"1\",\"experimental\":true}",
            "{\"operation\":24}",
            "{\"operation\":24,\"appid\":\"1\",\"appids\":[\"1\"]}",
            "{\"operation\":25,\"appids\":[\"1\"],\"appid\":\"1\"}",
            "{\"operation\":25,\"appids\":[\"1\"],\"experimental\":true}",
            "{\"operation\":25,\"appids\":[null]}",
        })
        {
            Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.DeserializeRequest(payload));
        }
    }

    [Fact]
    public void TheReportAndTheCompatListRoundTrip()
    {
        var response = new UpscalersResponse
        {
            Status = UpscalersResponseStatus.Ok,
            Diagnosis = new UpscalerDiagnosis
            {
                AppId = "100",
                IniDrift = UpscalerDiagnosisIniDrift.From(new IniDrift(IniDrift.Changed, 5, 6, new[] { new IniChange("Log.LogLevel", "2", null) })),
                Advanced = new[] { new UpscalerDiagnosisEdit { Key = "Tweaks.Scale", ValueOmitted = true } },
                Ini = new UpscalerDiagnosisIni { Missing = true },
            },
            Compat = new UpscalerCompat { Complete = false, Games = new[] { new UpscalerCompatEntry { AppId = "100", Inputs = new[] { "dlss" }, Preferred = "fsr-3.1" } } },
        };

        var parsed = UpscalersWireCodec.DeserializeResponse(UpscalersWireCodec.SerializeResponse(response));

        Assert.Equal(("changed", 5d, "Log.LogLevel"), (parsed.Diagnosis!.IniDrift!.Status, parsed.Diagnosis.IniDrift.WrittenAt, parsed.Diagnosis.IniDrift.Keys![0].Key));
        Assert.Null(parsed.Diagnosis.IniDrift.Keys[0].Now);
        Assert.True(parsed.Diagnosis.Advanced![0].ValueOmitted);
        Assert.False(parsed.Compat!.Complete);
        Assert.Equal(("dlss", "fsr-3.1"), (parsed.Compat.Games[0].Inputs[0], parsed.Compat.Games[0].Preferred));
        Assert.Throws<InvalidDataException>(() => UpscalersWireCodec.SerializeResponse(new UpscalersResponse
        {
            Status = UpscalersResponseStatus.Ok,
            Compat = new UpscalerCompat { Games = new[] { new UpscalerCompatEntry { AppId = "1" }, new UpscalerCompatEntry { AppId = "1" } } },
        }));
    }
}
