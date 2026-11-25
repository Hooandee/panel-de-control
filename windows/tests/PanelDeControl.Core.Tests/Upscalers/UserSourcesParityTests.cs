using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// The mod layout and the judging of the files a recipe asks the user for must give the Linux backend's answers for every
/// case of user_sources_parity.json (written by tests/test_upscalers_user_sources_parity.py).
/// </summary>
public sealed class UserSourcesParityTests
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "user_sources_parity.json")))!.AsObject();

    [Fact]
    public void FilenameVersionsMatch()
    {
        var cases = Fixture["filename_version"]!.AsArray();
        Assert.True(cases.Count > 10);
        foreach (var item in cases)
        {
            Assert.Equal(item!["version"]?.GetValue<string>(), UserFiles.FilenameVersion(item["name"]!.GetValue<string>()));
        }
    }

    [Fact]
    public void DllVersionsMatch()
    {
        var cases = Fixture["dll_version"]!.AsArray();
        Assert.True(cases.Count > 5);
        foreach (var item in cases)
        {
            var strings = item!["strings"]!.AsObject().ToDictionary(pair => pair.Key, pair => pair.Value!.GetValue<string>(), StringComparer.Ordinal);
            Assert.Equal(item["version"]?.GetValue<string>(), UserFiles.DllVersion(strings));
        }
    }

    [Fact]
    public void UnsafeMembersMatch()
    {
        var cases = Fixture["unsafe"]!.AsArray();
        Assert.True(cases.Count > 10);
        foreach (var item in cases)
        {
            Assert.True(item!["unsafe"]!.GetValue<bool>() == UserFiles.Unsafe(item["member"]!.GetValue<string>()), item["member"]!.GetValue<string>());
        }
    }

    [Fact]
    public void LocatingTheWantedFilesMatches()
    {
        var cases = Fixture["locate"]!.AsArray();
        Assert.True(cases.Count > 10);
        foreach (var item in cases)
        {
            var name = item!["name"]!.GetValue<string>();
            var dependency = Dependency(item["files"]!.AsObject());
            var members = item["members"]!.AsArray().Select(member => member!.GetValue<string>()).ToList();
            var expected = item["result"]!.AsObject();
            try
            {
                var found = UserFiles.Locate(dependency, item["file"]!.GetValue<string>(), () => members);
                Assert.True(expected.ContainsKey("ok"), name);
                Assert.Equal(expected["ok"]!.AsArray().Select(pair => (pair![0]!.GetValue<string>(), pair[1]!.GetValue<string>())),
                    found.Select(pair => (pair.Key, pair.Value)));
            }
            catch (UserSourceException error)
            {
                Assert.Equal(expected["error"]?.GetValue<string>(), error.Code);
            }
        }
    }

    [Fact]
    public void TheStateOfAFileMatches()
    {
        var cases = Fixture["state"]!.AsArray();
        Assert.True(cases.Count >= 7);
        foreach (var item in cases)
        {
            var dependency = Dependency(item!["files"]!.AsObject(), item["required"]?.GetValue<string>(),
                item["avoid"]!.AsArray().Select(version => version!.GetValue<string>()).ToArray());
            Assert.Equal(item["state"]!.GetValue<string>(), UserFiles.State(dependency, item["version"]?.GetValue<string>()));
            var outcome = RecipeDependencyPlan.UserFileOutcome(dependency, item["version"]?.GetValue<string>());
            Assert.Equal(item["state"]!.GetValue<string>() switch
            {
                "avoid" => DependencyOutcome.UserFileAvoid,
                "other_version" => DependencyOutcome.UserFileOtherVersion,
                _ => DependencyOutcome.UserFileReady,
            }, outcome);
        }
    }

    [Fact]
    public void TheLayoutOfAModMatches()
    {
        var cases = Fixture["layout"]!.AsArray();
        Assert.True(cases.Count > 15);
        foreach (var item in cases)
        {
            var name = item!["name"]!.GetValue<string>();
            var expected = item["result"]!.AsObject();
            try
            {
                var found = UserMods.Layout(Strings(item["members"]!), item["target"]!.GetValue<string>(), Strings(item["existing"]!), Strings(item["root_dirs"]!));
                Assert.True(expected.ContainsKey("ok"), name);
                Assert.Equal(expected["ok"]!.AsArray().Select(pair => (pair![0]!.GetValue<string>(), pair[1]!.GetValue<string>())),
                    found.Select(pair => (pair.Key, pair.Value)));
            }
            catch (UserSourceException error)
            {
                Assert.Equal(expected["error"]?.GetValue<string>(), error.Code);
            }
        }
    }

    [Fact]
    public void WhatReplacesOptiScalerMatches()
    {
        var cases = Fixture["replaces_optiscaler"]!.AsArray();
        Assert.True(cases.Count > 15);
        foreach (var item in cases)
        {
            var destinations = Strings(item!["destinations"]!);
            Assert.True(item["replaces"]!.GetValue<bool>() == UserMods.ReplacesOptiScaler(destinations), string.Join(",", destinations));
        }
    }

    private static List<string> Strings(JsonNode node) => node.AsArray().Select(item => item!.GetValue<string>()).ToList();

    private static RecipeDependency Dependency(JsonObject files, string? version = null, string[]? avoid = null)
    {
        var dependency = (RecipeDependency)Activator.CreateInstance(typeof(RecipeDependency), true)!;
        typeof(RecipeDependency).GetProperty(nameof(RecipeDependency.Files))!.SetValue(dependency, files.ToDictionary(pair => pair.Key, pair => pair.Value!.GetValue<string>(), StringComparer.Ordinal));
        typeof(RecipeDependency).GetProperty(nameof(RecipeDependency.Version))!.SetValue(dependency, version);
        typeof(RecipeDependency).GetProperty(nameof(RecipeDependency.AvoidVersions))!.SetValue(dependency, avoid ?? Array.Empty<string>());
        return dependency;
    }
}
