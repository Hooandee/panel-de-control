using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class GameBarFocusTrackerTests
{
    private static readonly IntPtr Steam = new(10);
    private static readonly IntPtr Bar = new(20);
    private static readonly IntPtr Desktop = new(30);
    private static readonly IntPtr Notepad = new(40);

    [Fact]
    public void ReturnsFocusToSteamWhenGameBarClosesOntoTheDesktop()
    {
        var tracker = new GameBarFocusTracker();

        tracker.Observe(new ForegroundWindow(Steam, ForegroundKind.Steam));
        tracker.Observe(new ForegroundWindow(Bar, ForegroundKind.GameBar));

        Assert.Equal(Steam, tracker.Observe(new ForegroundWindow(Desktop, ForegroundKind.Shell)));
        Assert.Equal(IntPtr.Zero, tracker.Observe(new ForegroundWindow(Desktop, ForegroundKind.Shell)));
    }

    [Fact]
    public void LeavesFocusAloneWhenAnotherAppTakesOver()
    {
        var tracker = new GameBarFocusTracker();
        tracker.Observe(new ForegroundWindow(Steam, ForegroundKind.Steam));
        tracker.Observe(new ForegroundWindow(Bar, ForegroundKind.GameBar));

        Assert.Equal(IntPtr.Zero, tracker.Observe(new ForegroundWindow(Notepad, ForegroundKind.Other)));
        Assert.Equal(IntPtr.Zero, tracker.Observe(new ForegroundWindow(Desktop, ForegroundKind.Shell)));
    }

    [Fact]
    public void LeavesFocusAloneWhenGameBarOpenedOverSomethingElse()
    {
        var tracker = new GameBarFocusTracker();
        tracker.Observe(new ForegroundWindow(Notepad, ForegroundKind.Other));
        tracker.Observe(new ForegroundWindow(Bar, ForegroundKind.GameBar));

        Assert.Equal(IntPtr.Zero, tracker.Observe(new ForegroundWindow(Desktop, ForegroundKind.Shell)));
    }

    [Fact]
    public void ReturningToSteamDirectlyNeedsNothing()
    {
        var tracker = new GameBarFocusTracker();
        tracker.Observe(new ForegroundWindow(Steam, ForegroundKind.Steam));
        tracker.Observe(new ForegroundWindow(Bar, ForegroundKind.GameBar));

        Assert.Equal(IntPtr.Zero, tracker.Observe(new ForegroundWindow(Steam, ForegroundKind.Steam)));
    }
}
