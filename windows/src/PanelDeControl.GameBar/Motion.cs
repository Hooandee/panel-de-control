using System;
using System.Numerics;
using Windows.Foundation;
using Windows.UI;
using Windows.UI.Composition;
using Windows.UI.ViewManagement;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Hosting;
using Windows.UI.Xaml.Media;
using Windows.UI.Xaml.Media.Animation;

namespace PanelDeControl.GameBar;

/// <summary>
/// Motion of the widget. Loops and transitions run on the composition thread so they never cost the
/// UI thread (or the game) a frame; everything collapses to instant changes when Windows animations are off.
/// </summary>
internal static class Motion
{
    private static readonly TimeSpan GlideLength = TimeSpan.FromMilliseconds(380);
    private static readonly UISettings Settings = new();
    private static Storyboard? glide;

    // Read every time: the user can turn Windows animations off while the widget is running.
    public static bool Enabled
    {
        get
        {
            try
            {
                return Settings.AnimationsEnabled;
            }
            catch
            {
                return true;
            }
        }
    }

    public static void Glide(FrameworkElement indicator, TranslateTransform transform, double x, double width, bool animate)
    {
        // A finished storyboard holds its end values over local ones, so it is stopped before placing directly
        // and the end values are written locally once it completes. Stopping one mid-way snaps back to where it
        // started, so the spot it had reached is kept locally first and the next glide continues from there.
        if (glide is not null)
        {
            var reachedX = transform.X;
            var reachedWidth = indicator.Width;
            glide.Stop();
            transform.X = reachedX;
            indicator.Width = reachedWidth;
            glide = null;
        }
        if (!animate || !Enabled || indicator.Width is not > 0)
        {
            transform.X = x;
            indicator.Width = width;
            return;
        }

        var ease = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.3 };
        var move = new DoubleAnimation { To = x, Duration = GlideLength, EasingFunction = ease };
        Storyboard.SetTarget(move, transform);
        Storyboard.SetTargetProperty(move, "X");
        // Width is a layout property, so the animation is dependent; the indicator is a single small element.
        var grow = new DoubleAnimation { To = width, Duration = GlideLength, EasingFunction = ease, EnableDependentAnimation = true };
        Storyboard.SetTarget(grow, indicator);
        Storyboard.SetTargetProperty(grow, "Width");
        var storyboard = new Storyboard();
        storyboard.Children.Add(move);
        storyboard.Children.Add(grow);
        storyboard.Completed += (_, _) =>
        {
            transform.X = x;
            indicator.Width = width;
            storyboard.Stop();
        };
        glide = storyboard;
        storyboard.Begin();
    }

    public static void PrepareEntrance(UIElement element, int direction)
    {
        if (!Enabled)
        {
            return;
        }

        try
        {
            var compositor = ElementCompositionPreview.GetElementVisual(element).Compositor;
            ElementCompositionPreview.SetIsTranslationEnabled(element, true);
            var ease = compositor.CreateCubicBezierEasingFunction(new Vector2(0.16f, 1f), new Vector2(0.3f, 1f));

            var fadeIn = compositor.CreateScalarKeyFrameAnimation();
            fadeIn.Target = "Opacity";
            fadeIn.InsertKeyFrame(0, 0);
            fadeIn.InsertKeyFrame(1, 1, ease);
            fadeIn.Duration = TimeSpan.FromMilliseconds(320);
            var slideIn = compositor.CreateVector3KeyFrameAnimation();
            slideIn.Target = "Translation";
            slideIn.InsertKeyFrame(0, new Vector3(28 * Math.Sign(direction), direction == 0 ? 14 : 0, 0));
            slideIn.InsertKeyFrame(1, Vector3.Zero, ease);
            slideIn.Duration = TimeSpan.FromMilliseconds(420);
            var show = compositor.CreateAnimationGroup();
            show.Add(fadeIn);
            show.Add(slideIn);
            ElementCompositionPreview.SetImplicitShowAnimation(element, show);

            var fadeOut = compositor.CreateScalarKeyFrameAnimation();
            fadeOut.Target = "Opacity";
            fadeOut.InsertKeyFrame(1, 0);
            fadeOut.Duration = TimeSpan.FromMilliseconds(140);
            ElementCompositionPreview.SetImplicitHideAnimation(element, fadeOut);
        }
        catch (Exception exception)
        {
            CrashLog.Write("motion-entrance", exception);
        }
    }

    public static void StopBreathing(UIElement element) =>
        ElementCompositionPreview.GetElementVisual(element).StopAnimation("Opacity");

    public static void Breathe(UIElement element, float low, float high, TimeSpan period)
    {
        if (!Enabled)
        {
            return;
        }

        try
        {
            var visual = ElementCompositionPreview.GetElementVisual(element);
            var breathe = visual.Compositor.CreateScalarKeyFrameAnimation();
            breathe.InsertKeyFrame(0, high);
            breathe.InsertKeyFrame(0.5f, low);
            breathe.InsertKeyFrame(1, high);
            breathe.Duration = period;
            breathe.IterationBehavior = AnimationIterationBehavior.Forever;
            visual.StartAnimation("Opacity", breathe);
        }
        catch (Exception exception)
        {
            CrashLog.Write("motion-breathe", exception);
        }
    }

    public static void Pop(FrameworkElement element)
    {
        if (!Enabled || element.ActualWidth <= 0)
        {
            return;
        }

        var visual = ElementCompositionPreview.GetElementVisual(element);
        visual.CenterPoint = new Vector3((float)element.ActualWidth / 2, (float)element.ActualHeight / 2, 0);
        var pop = visual.Compositor.CreateVector3KeyFrameAnimation();
        pop.InsertKeyFrame(0.35f, new Vector3(1.07f, 1.07f, 1));
        pop.InsertKeyFrame(1, Vector3.One);
        pop.Duration = TimeSpan.FromMilliseconds(320);
        visual.StartAnimation("Scale", pop);
    }

    public static void Spin(FrameworkElement element)
    {
        if (!Enabled)
        {
            return;
        }

        if (element.RenderTransform is not RotateTransform rotate)
        {
            rotate = new RotateTransform();
            element.RenderTransform = rotate;
            element.RenderTransformOrigin = new Point(0.5, 0.5);
        }

        var spin = new DoubleAnimation
        {
            From = 0,
            To = 360,
            Duration = TimeSpan.FromMilliseconds(620),
            EasingFunction = new CubicEase { EasingMode = EasingMode.EaseInOut },
        };
        Storyboard.SetTarget(spin, rotate);
        Storyboard.SetTargetProperty(spin, "Angle");
        var storyboard = new Storyboard();
        storyboard.Children.Add(spin);
        storyboard.Begin();
    }

    // Light drifting behind the glass surfaces: they read as glass without a backdrop blur, which would be
    // recomputed every frame over moving content and take GPU from the game.
    public sealed class Aurora
    {
        private const float BlobSize = 560;
        private readonly Compositor compositor;
        private readonly CompositionColorGradientStop[] stops;
        private readonly SpriteVisual[] blobs;
        private readonly Vector3KeyFrameAnimation[] drifts;

        public Aurora(UIElement host)
        {
            compositor = ElementCompositionPreview.GetElementVisual(host).Compositor;
            var container = compositor.CreateContainerVisual();
            var paths = new[]
            {
                (From: new Vector2(-250, -300), To: new Vector2(-60, -200), Seconds: 19, Strength: 1f),
                (From: new Vector2(120, -260), To: new Vector2(-40, -120), Seconds: 23, Strength: 0.75f),
                (From: new Vector2(-200, 220), To: new Vector2(80, 120), Seconds: 29, Strength: 0.45f),
            };
            stops = new CompositionColorGradientStop[paths.Length];
            blobs = new SpriteVisual[paths.Length];
            drifts = new Vector3KeyFrameAnimation[paths.Length];
            for (var index = 0; index < paths.Length; index++)
            {
                var path = paths[index];
                var brush = compositor.CreateRadialGradientBrush();
                stops[index] = compositor.CreateColorGradientStop(0, Colors.Transparent);
                brush.ColorStops.Add(stops[index]);
                brush.ColorStops.Add(compositor.CreateColorGradientStop(1, Colors.Transparent));
                var blob = compositor.CreateSpriteVisual();
                blob.Size = new Vector2(BlobSize, BlobSize);
                blob.Brush = brush;
                blob.Opacity = path.Strength;
                blob.Offset = new Vector3(path.From, 0);
                var drift = compositor.CreateVector3KeyFrameAnimation();
                drift.InsertKeyFrame(0, new Vector3(path.From, 0));
                drift.InsertKeyFrame(0.5f, new Vector3(path.To, 0));
                drift.InsertKeyFrame(1, new Vector3(path.From, 0));
                drift.Duration = TimeSpan.FromSeconds(path.Seconds);
                drift.IterationBehavior = AnimationIterationBehavior.Forever;
                blobs[index] = blob;
                drifts[index] = drift;
                container.Children.InsertAtTop(blob);
            }

            ElementCompositionPreview.SetElementChildVisual(host, container);
        }

        // Endless loops keep the compositor producing frames, so they only run while the widget is on screen.
        public void Run(bool running)
        {
            for (var index = 0; index < blobs.Length; index++)
            {
                if (running && Enabled)
                {
                    blobs[index].StartAnimation("Offset", drifts[index]);
                }
                else
                {
                    blobs[index].StopAnimation("Offset");
                }
            }
        }

        public void Tint(Color primary, Color secondary)
        {
            var targets = new[] { primary, secondary, primary };
            for (var index = 0; index < stops.Length; index++)
            {
                if (!Enabled)
                {
                    stops[index].Color = targets[index];
                    continue;
                }

                var shift = compositor.CreateColorKeyFrameAnimation();
                shift.InsertKeyFrame(1, targets[index]);
                shift.Duration = TimeSpan.FromMilliseconds(700);
                stops[index].StartAnimation("Color", shift);
            }
        }
    }
}
