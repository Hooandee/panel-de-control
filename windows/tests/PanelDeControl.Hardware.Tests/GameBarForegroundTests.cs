using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

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

    private static readonly DateTimeOffset Raised = new(2026, 11, 17, 20, 30, 26, TimeSpan.Zero);

    [Fact]
    public void ClosingGameBarRightAfterTheRaiseDoesNotLetBigPictureGo()
    {
        var foreground = new GameBarForeground();
        foreground.BigPictureHeld(Raised);

        Assert.False(foreground.GameTookForeground(Raised.AddMilliseconds(500)));
        Assert.True(foreground.GameTookForeground(Raised.AddSeconds(5)));
    }

    [Fact]
    public void TheGameTakingTheForegroundOnlyCountsWhileBigPictureIsHeld()
    {
        var foreground = new GameBarForeground();

        Assert.False(foreground.GameTookForeground(Raised.AddSeconds(5)));

        foreground.BigPictureHeld(Raised);
        foreground.BigPictureLet();
        Assert.False(foreground.GameTookForeground(Raised.AddSeconds(5)));
    }

    [Fact]
    public void BigPictureGivesWayOnlyOnce()
    {
        var foreground = new GameBarForeground();
        foreground.BigPictureHeld(Raised);

        Assert.True(foreground.GameTookForeground(Raised.AddSeconds(5)));
        Assert.False(foreground.GameTookForeground(Raised.AddSeconds(6)));
    }
}
