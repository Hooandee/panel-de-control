using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

// On a ROG Xbox Ally X an open Game Bar reads as the shell's immersive window, and after Big Picture was raised by
// window order Windows kept reporting the shell in the foreground while Big Picture was on screen.
public sealed class GameBarForegroundTests
{
    [Fact]
    public void GameBarOverTheShellCountsWhatThePlayerHadInFrontBefore()
    {
        var foreground = new GameBarForeground();

        foreground.Observe(ForegroundKind.Other);
        foreground.Observe(ForegroundKind.Shell);
        foreground.Observe(ForegroundKind.GameBar);

        Assert.Equal(ForegroundKind.Other, foreground.BeforeGameBar(ForegroundKind.Shell));
        Assert.Equal(ForegroundKind.Steam, foreground.BeforeGameBar(ForegroundKind.Steam));
    }

    [Fact]
    public void BigPictureRaisedByWindowOrderCountsWhileWindowsStillReportsTheGame()
    {
        var foreground = new GameBarForeground();
        foreground.Observe(ForegroundKind.Other);

        foreground.BigPictureRaised(byOrder: true);

        Assert.Equal(ForegroundKind.Steam, foreground.BeforeGameBar(ForegroundKind.Other));
        Assert.Equal(ForegroundKind.Steam, foreground.BeforeGameBar(ForegroundKind.Shell));
    }

    [Fact]
    public void AFailedRaiseNotesNothing()
    {
        var foreground = new GameBarForeground();
        foreground.Observe(ForegroundKind.Other);

        foreground.BigPictureRaised(byOrder: false);

        Assert.Equal(ForegroundKind.Other, foreground.BeforeGameBar(ForegroundKind.Shell));
        Assert.False(foreground.GameResumed());
    }

    [Fact]
    public void TheNoteExpiresOnceWindowsReportsAnotherWindowInFront()
    {
        var foreground = new GameBarForeground();
        foreground.BigPictureRaised(byOrder: true);

        // The player went back to the game with Alt+Tab or Xbox's switcher.
        foreground.Observe(ForegroundKind.Other);

        Assert.Equal(ForegroundKind.Other, foreground.BeforeGameBar(ForegroundKind.Shell));
    }

    [Fact]
    public void ResumingTheGameCountsTheGameAndAsksForItsRaiseOnlyAfterARaiseByOrder()
    {
        var foreground = new GameBarForeground();
        foreground.BigPictureRaised(byOrder: true);

        Assert.True(foreground.GameResumed());
        Assert.Equal(ForegroundKind.Other, foreground.BeforeGameBar(ForegroundKind.Shell));
        Assert.False(foreground.GameResumed());
    }

    [Fact]
    public void AGameThatEndedLeavesNothingToRaiseForTheNextOne()
    {
        var foreground = new GameBarForeground();
        foreground.BigPictureRaised(byOrder: true);

        foreground.GameEnded();

        Assert.False(foreground.GameResumed());
    }
}
