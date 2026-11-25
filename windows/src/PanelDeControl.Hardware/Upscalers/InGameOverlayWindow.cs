using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>What the badge window shows and on which game's monitor.</summary>
public sealed record OverlayFrame(IReadOnlyList<BadgeLine> Lines, IntPtr GameWindow);

public interface IInGameOverlay
{
    /// <summary>Shows the frame, or fades the badge out when it is null. Never blocks on drawing.</summary>
    void Present(OverlayFrame? frame);
}

/// <summary>
/// The badge as its own small window above the game, never injected into it: a layered, click-through, no-activate
/// topmost popup on a thread of its own, so it takes no focus and no input. It cannot show over true exclusive
/// fullscreen, only over borderless and flip-model windows.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class InGameOverlayWindow : IInGameOverlay, IDisposable
{
    private const string ClassName = "PanelDeControl.InGameBadge";
    private const int Opacity = 235;
    private const double FadeMilliseconds = 320;
    private const uint PresentMessage = 0x8001;
    private const uint QuitMessage = 0x8002;

    private const uint WsPopup = 0x80000000;
    private const uint WsExToolWindow = 0x00000080;
    private const uint WsExTopmost = 0x00000008;
    private const uint WsExTransparent = 0x00000020;
    private const uint WsExLayered = 0x00080000;
    private const uint WsExNoActivate = 0x08000000;

    private const uint WmDestroy = 0x0002;
    private const uint WmPaint = 0x000F;
    private const uint WmEraseBackground = 0x0014;
    private const uint WmNcHitTest = 0x0084;
    private const uint WmMouseActivate = 0x0021;
    private const uint WmTimer = 0x0113;

    private const uint SwHide = 0;
    private const uint SwShowNoActivate = 4;
    private const uint SwpNoSize = 0x0001;
    private const uint SwpNoMove = 0x0002;
    private const uint SwpNoActivate = 0x0010;
    private const uint LwaAlpha = 0x2;
    private const uint DtLeft = 0x0000;
    private const uint DtVCenter = 0x0004;
    private const uint DtSingleLine = 0x0020;
    private const uint DtNoPrefix = 0x0800;
    private const uint DtNoClip = 0x0100;
    private const int FadeTimer = 1;
    private const int TopmostTimer = 2;
    private static readonly IntPtr HwndTopmost = new(-1);
    private static readonly IntPtr PerMonitorAwareV2 = new(-4);

    private static readonly WndProc Procedure = HandleMessage;
    private static InGameOverlayWindow? current;

    private readonly object gate = new();
    private readonly ManualResetEventSlim ready = new(false);
    private Thread? thread;
    private IntPtr window;
    private OverlayFrame? pending;
    private volatile bool disposed;
    private readonly OverlayBackoff backoff = new();
    private IntPtr gameWindow;

    private string layoutKey = string.Empty;
    private IntPtr font;
    private List<DrawnLine> drawn = new();
    private int sizeWidth;
    private int sizeHeight;
    private bool shown;
    private double alpha;
    private double fadeFrom;
    private double fadeTo;
    private long fadeStarted;

    private delegate IntPtr WndProc(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    public void Present(OverlayFrame? frame)
    {
        lock (gate)
        {
            if (disposed || (frame is null && window == IntPtr.Zero))
            {
                return;
            }

            pending = frame;
            if (window == IntPtr.Zero)
            {
                if (!backoff.CanStart(DateTimeOffset.UtcNow))
                {
                    return;
                }

                Start();
                if (window == IntPtr.Zero)
                {
                    return;
                }
            }
        }

        PostMessage(window, PresentMessage, IntPtr.Zero, IntPtr.Zero);
    }

    public void Dispose()
    {
        IntPtr handle;
        lock (gate)
        {
            handle = window;
            disposed = true;
        }

        if (handle != IntPtr.Zero)
        {
            PostMessage(handle, QuitMessage, IntPtr.Zero, IntPtr.Zero);
            thread?.Join(TimeSpan.FromSeconds(1));
        }
    }

    private void Start()
    {
        if (thread is not { IsAlive: true })
        {
            ready.Reset();
            thread = new Thread(Run) { IsBackground = true, Name = "PanelDeControl.InGameBadge" };
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
        }

        if (!ready.Wait(TimeSpan.FromSeconds(3)) || window == IntPtr.Zero)
        {
            Fail("create", "badge window not created");
        }
    }

    private void Fail(string kind, string detail)
    {
        if (backoff.Failed(DateTimeOffset.UtcNow, kind))
        {
            CompanionLog.Write("upscalers.ingame", detail);
        }
    }

    private void Run()
    {
        string? failure = null;
        string? detail = null;
        try
        {
            SetThreadDpiAwarenessContext(PerMonitorAwareV2);
            var instance = GetModuleHandle(null);
            var wndClass = new WndClassEx
            {
                Size = (uint)Marshal.SizeOf<WndClassEx>(),
                WndProc = Marshal.GetFunctionPointerForDelegate(Procedure),
                Instance = instance,
                ClassName = ClassName,
            };
            RegisterClassEx(ref wndClass);
            current = this;
            var handle = CreateWindowEx(
                WsExLayered | WsExTransparent | WsExTopmost | WsExToolWindow | WsExNoActivate,
                ClassName, string.Empty, WsPopup, 0, 0, 1, 1, IntPtr.Zero, IntPtr.Zero, instance, IntPtr.Zero);
            if (handle == IntPtr.Zero)
            {
                failure = "create";
                detail = "badge window creation failed";
                ready.Set();
                return;
            }

            SetLayeredWindowAttributes(handle, 0, 0, LwaAlpha);
            window = handle;
            ready.Set();
            while (GetMessage(out var message, IntPtr.Zero, 0, 0) > 0)
            {
                if (message.Value == QuitMessage)
                {
                    DestroyWindow(handle);
                    continue;
                }

                TranslateMessage(ref message);
                DispatchMessage(ref message);
            }
        }
        catch (Exception exception)
        {
            failure = "thread";
            detail = exception.ToString();
            ready.Set();
        }
        finally
        {
            window = IntPtr.Zero;
            if (font != IntPtr.Zero)
            {
                DeleteObject(font);
                font = IntPtr.Zero;
            }

            shown = false;
            alpha = 0;
            fadeFrom = 0;
            fadeTo = 0;
            layoutKey = string.Empty;
            if (!disposed)
            {
                Fail(failure ?? "ended", detail ?? "badge thread ended");
            }
        }
    }

    private static IntPtr HandleMessage(IntPtr handle, uint message, IntPtr wParam, IntPtr lParam)
    {
        try
        {
            switch (message)
            {
                case WmNcHitTest:
                    return new IntPtr(-1);
                case WmMouseActivate:
                    return new IntPtr(3);
                case WmEraseBackground:
                    return new IntPtr(1);
                case PresentMessage:
                    current?.Apply(handle);
                    return IntPtr.Zero;
                case WmTimer:
                    current?.Tick(handle, wParam.ToInt32());
                    return IntPtr.Zero;
                case WmPaint:
                    current?.Paint(handle);
                    return IntPtr.Zero;
                case WmDestroy:
                    PostQuitMessage(0);
                    return IntPtr.Zero;
            }
        }
        catch (Exception exception)
        {
            CompanionLog.Write("upscalers.ingame.window", exception);
        }

        return DefWindowProc(handle, message, wParam, lParam);
    }

    private void Apply(IntPtr handle)
    {
        OverlayFrame? frame;
        lock (gate)
        {
            frame = pending;
        }

        if (frame is null || frame.Lines.Count == 0)
        {
            FadeTo(handle, 0);
            return;
        }

        gameWindow = frame.GameWindow;
        var place = Place(frame.GameWindow);
        var key = Key(frame, place);
        if (key != layoutKey)
        {
            Layout(handle, frame, place);
            layoutKey = key;
        }

        if (!shown)
        {
            ShowWindow(handle, SwShowNoActivate);
            SetWindowPos(handle, HwndTopmost, 0, 0, 0, 0, SwpNoMove | SwpNoSize | SwpNoActivate);
            shown = true;
            SetTimer(handle, new IntPtr(TopmostTimer), 1000, IntPtr.Zero);
        }

        FadeTo(handle, Opacity);
    }

    private static string Key(OverlayFrame frame, Placement place) =>
        frame.GameWindow + "|" + place.Monitor + "|" + place.Dpi + "|" + place.Bounds.Left + "," + place.Bounds.Top + "," + place.Bounds.Right + "|" + string.Join("\n", frame.Lines.Select(line => string.Join("\t", line.Spans.Select(span => span.Tone + span.Text))));

    private void FadeTo(IntPtr handle, double target)
    {
        if (!shown && target == 0)
        {
            return;
        }

        if (fadeTo == target)
        {
            return;
        }

        fadeFrom = alpha;
        fadeTo = target;
        fadeStarted = Stopwatch.GetTimestamp();
        SetTimer(handle, new IntPtr(FadeTimer), 16, IntPtr.Zero);
    }

    private void Tick(IntPtr handle, int timer)
    {
        if (timer == TopmostTimer)
        {
            if (shown && NeedsRaise(handle))
            {
                SetWindowPos(handle, HwndTopmost, 0, 0, 0, 0, SwpNoMove | SwpNoSize | SwpNoActivate);
            }

            return;
        }

        var elapsed = Stopwatch.GetElapsedTime(fadeStarted).TotalMilliseconds;
        var progress = Math.Min(1, elapsed / FadeMilliseconds);
        alpha = fadeFrom + ((fadeTo - fadeFrom) * progress);
        SetLayeredWindowAttributes(handle, 0, (byte)Math.Round(alpha), LwaAlpha);
        if (progress < 1)
        {
            return;
        }

        KillTimer(handle, new IntPtr(FadeTimer));
        if (fadeTo == 0 && shown)
        {
            ShowWindow(handle, SwHide);
            KillTimer(handle, new IntPtr(TopmostTimer));
            shown = false;
            layoutKey = string.Empty;
        }
    }

    private bool NeedsRaise(IntPtr handle) =>
        (GetWindowLong(handle, -20) & WsExTopmost) == 0
        || OverlayZOrder.GameIsAbove(handle, gameWindow, window => GetWindow(window, 3));

    private readonly record struct Placement(IntPtr Monitor, Rect Bounds, uint Dpi);

    private static Placement Place(IntPtr gameWindow)
    {
        var monitor = MonitorFromWindow(gameWindow, 2);
        var info = new MonitorInfo { Size = (uint)Marshal.SizeOf<MonitorInfo>() };
        if (!GetMonitorInfo(monitor, ref info))
        {
            info.Monitor = new Rect { Left = 0, Top = 0, Right = 1920, Bottom = 1080 };
        }

        uint dpi = 96;
        try
        {
            if (monitor != IntPtr.Zero && GetDpiForMonitor(monitor, 0, out var dpiX, out _) == 0 && dpiX > 0)
            {
                dpi = dpiX;
            }
        }
        catch (Exception exception) when (exception is DllNotFoundException or EntryPointNotFoundException)
        {
        }

        return new Placement(monitor, info.Monitor, dpi);
    }

    private void Layout(IntPtr handle, OverlayFrame frame, Placement place)
    {
        var info = new MonitorInfo { Monitor = place.Bounds };
        var scale = place.Dpi / 96.0;
        int Px(double value) => (int)Math.Round(value * scale);
        if (font != IntPtr.Zero)
        {
            DeleteObject(font);
        }

        font = CreateFont(-Px(11), 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI");
        var measure = CreateCompatibleDC(IntPtr.Zero);
        var previous = SelectObject(measure, font);
        var lines = new List<DrawnLine>();
        var boxHeight = Px(15) + (2 * Px(3));
        var gap = Px(4);
        var padding = Px(10);
        var spanGap = Px(8);
        var widest = 0;
        foreach (var line in frame.Lines)
        {
            var spans = new List<(string Text, BadgeTone Tone, int Width)>();
            var width = 2 * padding;
            foreach (var span in line.Spans)
            {
                GetTextExtentPoint32(measure, span.Text, span.Text.Length, out var size);
                spans.Add((span.Text, span.Tone, size.Width));
                width += size.Width + (spans.Count > 1 ? spanGap : 0);
            }

            lines.Add(new DrawnLine(spans, width));
            widest = Math.Max(widest, width);
        }

        SelectObject(measure, previous);
        DeleteDC(measure);

        var totalHeight = (lines.Count * boxHeight) + ((lines.Count - 1) * gap);
        var region = CreateRectRgn(0, 0, 0, 0);
        var top = 0;
        foreach (var line in lines)
        {
            line.Left = (widest - line.Width) / 2;
            line.Top = top;
            line.Height = boxHeight;
            line.Padding = padding;
            line.SpanGap = spanGap;
            var round = CreateRoundRectRgn(line.Left, top, line.Left + line.Width + 1, top + boxHeight + 1, 2 * Px(8), 2 * Px(8));
            CombineRgn(region, region, round, 2);
            DeleteObject(round);
            top += boxHeight + gap;
        }

        drawn = lines;
        sizeWidth = widest;
        sizeHeight = totalHeight;
        SetWindowRgn(handle, region, true);
        var monitorWidth = info.Monitor.Right - info.Monitor.Left;
        SetWindowPos(
            handle,
            HwndTopmost,
            info.Monitor.Left + ((monitorWidth - widest) / 2),
            info.Monitor.Top + Px(10),
            widest,
            totalHeight,
            SwpNoActivate);
        InvalidateRect(handle, IntPtr.Zero, true);
    }

    private void Paint(IntPtr handle)
    {
        var paint = new PaintStruct();
        var dc = BeginPaint(handle, out paint);
        try
        {
            var background = CreateSolidBrush(Color(0x15, 0x18, 0x1e));
            var client = new Rect { Left = 0, Top = 0, Right = sizeWidth, Bottom = sizeHeight };
            FillRect(dc, ref client, background);
            DeleteObject(background);
            var previous = SelectObject(dc, font);
            SetBkMode(dc, 1);
            foreach (var line in drawn)
            {
                var x = line.Left + line.Padding;
                foreach (var (text, tone, width) in line.Spans)
                {
                    SetTextColor(dc, tone switch
                    {
                        BadgeTone.Muted => Color(0x9a, 0xa3, 0xae),
                        BadgeTone.Warn => Color(0xff, 0xbe, 0x63),
                        _ => Color(0xee, 0xf1, 0xf5),
                    });
                    var cell = new Rect { Left = x, Top = line.Top, Right = x + width + 2, Bottom = line.Top + line.Height };
                    DrawText(dc, text, text.Length, ref cell, DtLeft | DtVCenter | DtSingleLine | DtNoPrefix | DtNoClip);
                    x += width + line.SpanGap;
                }
            }

            SelectObject(dc, previous);
        }
        finally
        {
            EndPaint(handle, ref paint);
        }
    }

    private static uint Color(byte red, byte green, byte blue) => (uint)(red | (green << 8) | (blue << 16));

    private sealed class DrawnLine
    {
        public DrawnLine(List<(string Text, BadgeTone Tone, int Width)> spans, int width)
        {
            Spans = spans;
            Width = width;
        }

        public List<(string Text, BadgeTone Tone, int Width)> Spans { get; }

        public int Width { get; }

        public int Left { get; set; }

        public int Top { get; set; }

        public int Height { get; set; }

        public int Padding { get; set; }

        public int SpanGap { get; set; }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WndClassEx
    {
        public uint Size;
        public uint Style;
        public IntPtr WndProc;
        public int ClassExtra;
        public int WindowExtra;
        public IntPtr Instance;
        public IntPtr Icon;
        public IntPtr Cursor;
        public IntPtr Background;
        public string? MenuName;
        public string ClassName;
        public IntPtr SmallIcon;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Rect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TextSize
    {
        public int Width;
        public int Height;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Msg
    {
        public IntPtr Window;
        public uint Value;
        public IntPtr WParam;
        public IntPtr LParam;
        public uint Time;
        public Point Position;

    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MonitorInfo
    {
        public uint Size;
        public Rect Monitor;
        public Rect Work;
        public uint Flags;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PaintStruct
    {
        public IntPtr Dc;
        public int Erase;
        public Rect Paint;
        public int Restore;
        public int IncUpdate;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)]
        public byte[] Reserved;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandle(string? name);

    [DllImport("user32.dll", EntryPoint = "RegisterClassExW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern ushort RegisterClassEx(ref WndClassEx wndClass);

    [DllImport("user32.dll", EntryPoint = "CreateWindowExW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateWindowEx(uint exStyle, string className, string windowName, uint style, int x, int y, int width, int height, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr parameter);

    [DllImport("user32.dll", EntryPoint = "DefWindowProcW")]
    private static extern IntPtr DefWindowProc(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", EntryPoint = "GetMessageW")]
    private static extern int GetMessage(out Msg message, IntPtr window, uint min, uint max);

    [DllImport("user32.dll")]
    private static extern bool TranslateMessage(ref Msg message);

    [DllImport("user32.dll", EntryPoint = "DispatchMessageW")]
    private static extern IntPtr DispatchMessage(ref Msg message);

    [DllImport("user32.dll", EntryPoint = "PostMessageW")]
    private static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern void PostQuitMessage(int code);

    [DllImport("user32.dll")]
    private static extern bool DestroyWindow(IntPtr window);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr window, uint command);

    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);

    [DllImport("user32.dll")]
    private static extern bool SetLayeredWindowAttributes(IntPtr window, uint key, byte alpha, uint flags);

    [DllImport("user32.dll")]
    private static extern int SetWindowRgn(IntPtr window, IntPtr region, bool redraw);

    [DllImport("user32.dll")]
    private static extern IntPtr SetTimer(IntPtr window, IntPtr id, uint elapse, IntPtr callback);

    [DllImport("user32.dll")]
    private static extern bool KillTimer(IntPtr window, IntPtr id);

    [DllImport("user32.dll")]
    private static extern bool InvalidateRect(IntPtr window, IntPtr rect, bool erase);

    [DllImport("user32.dll")]
    private static extern IntPtr BeginPaint(IntPtr window, out PaintStruct paint);

    [DllImport("user32.dll")]
    private static extern bool EndPaint(IntPtr window, ref PaintStruct paint);

    [DllImport("user32.dll")]
    private static extern int FillRect(IntPtr dc, ref Rect rect, IntPtr brush);

    [DllImport("user32.dll", EntryPoint = "DrawTextW", CharSet = CharSet.Unicode)]
    private static extern int DrawText(IntPtr dc, string text, int count, ref Rect rect, uint format);

    [DllImport("user32.dll", EntryPoint = "GetWindowLongW")]
    private static extern int GetWindowLong(IntPtr window, int index);

    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr window, uint command);

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromWindow(IntPtr window, uint flags);

    [DllImport("user32.dll", EntryPoint = "GetMonitorInfoW")]
    private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);

    [DllImport("user32.dll")]
    private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);

    [DllImport("shcore.dll")]
    private static extern int GetDpiForMonitor(IntPtr monitor, int type, out uint x, out uint y);

    [DllImport("gdi32.dll", EntryPoint = "CreateFontW", CharSet = CharSet.Unicode)]
    private static extern IntPtr CreateFont(int height, int width, int escapement, int orientation, int weight, uint italic, uint underline, uint strikeOut, uint charSet, uint outPrecision, uint clipPrecision, uint quality, uint pitchAndFamily, string face);

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateCompatibleDC(IntPtr dc);

    [DllImport("gdi32.dll")]
    private static extern bool DeleteDC(IntPtr dc);

    [DllImport("gdi32.dll")]
    private static extern IntPtr SelectObject(IntPtr dc, IntPtr obj);

    [DllImport("gdi32.dll")]
    private static extern bool DeleteObject(IntPtr obj);

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateSolidBrush(uint color);

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateRectRgn(int left, int top, int right, int bottom);

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateRoundRectRgn(int left, int top, int right, int bottom, int width, int height);

    [DllImport("gdi32.dll")]
    private static extern int CombineRgn(IntPtr destination, IntPtr first, IntPtr second, int mode);

    [DllImport("gdi32.dll")]
    private static extern int SetBkMode(IntPtr dc, int mode);

    [DllImport("gdi32.dll")]
    private static extern uint SetTextColor(IntPtr dc, uint color);

    [DllImport("gdi32.dll", EntryPoint = "GetTextExtentPoint32W", CharSet = CharSet.Unicode)]
    private static extern bool GetTextExtentPoint32(IntPtr dc, string text, int count, out TextSize size);
}
