using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>A cover Steam cached for a game, shrunk to what a list row needs.</summary>
public sealed class ScaledCover
{
    public ScaledCover(byte[] data, string mime)
    {
        Data = data;
        Mime = mime;
    }

    public byte[] Data { get; }

    public string Mime { get; }
}

/// <summary>
/// Steam's cached artwork for a game: the portrait first, then capsule and header images, in any language Steam cached
/// and in the appid folder or one level of subfolders.
/// </summary>
public static class CoverFiles
{
    public const long MaximumSourceBytes = 8 * 1024 * 1024;

    private static readonly System.Text.RegularExpressions.Regex Portrait =
        new(@"^library_600x900(_[A-Za-z0-9-]+)?\.(jpg|png)$", System.Text.RegularExpressions.RegexOptions.CultureInvariant | System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    private static readonly System.Text.RegularExpressions.Regex Capsule =
        new(@"^library_capsule[^/\\]*\.(jpg|png)$", System.Text.RegularExpressions.RegexOptions.CultureInvariant | System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    private static readonly System.Text.RegularExpressions.Regex Header =
        new(@"^header(_[A-Za-z0-9-]+)?\.(jpg|png)$", System.Text.RegularExpressions.RegexOptions.CultureInvariant | System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    private static readonly string[] Plain = { "library_600x900", "library_capsule", "header", "library_header", "capsule_616x353", "capsule_231x87" };

    private static readonly string[] Legacy = { "library_header.jpg", "capsule_616x353.jpg", "capsule_231x87.jpg" };

    public static byte[]? Find(IReadOnlyFileSystem fileSystem, IEnumerable<string> steamRoots, string appId)
    {
        foreach (var root in steamRoots)
        {
            var cache = root.Replace('\\', '/').TrimEnd('/') + "/appcache/librarycache";
            var folder = cache + "/" + appId;
            if (fileSystem.IsSymbolicLink(folder))
            {
                continue;
            }

            var folders = new List<(string Folder, List<string> Files)> { Entries(fileSystem, folder, out var children) };
            folders.AddRange(children.Select(child => Entries(fileSystem, child, out _)));
            foreach (var matches in new Func<string, bool>[] { Portrait.IsMatch, Capsule.IsMatch, Header.IsMatch, name => Legacy.Contains(name, StringComparer.OrdinalIgnoreCase) })
            {
                foreach (var (directory, files) in folders)
                {
                    foreach (var name in files.Where(matches).OrderBy(Rank).ThenBy(name => name, StringComparer.OrdinalIgnoreCase))
                    {
                        if (Read(fileSystem, directory + "/" + name) is { } bytes)
                        {
                            return bytes;
                        }
                    }
                }
            }

            foreach (var name in new[] { "library_600x900.jpg", "library_capsule.jpg", "library_600x900.png", "header.jpg" }.Concat(Legacy))
            {
                var path = cache + "/" + appId + "_" + name;
                if (!fileSystem.IsSymbolicLink(path) && Read(fileSystem, path) is { } bytes)
                {
                    return bytes;
                }
            }
        }

        return null;
    }

    // The plain name before a localized one, and JPEG before PNG.
    private static int Rank(string name) =>
        (Plain.Contains(Path.GetFileNameWithoutExtension(name), StringComparer.OrdinalIgnoreCase) ? 0 : 2)
        + (name.EndsWith(".png", StringComparison.OrdinalIgnoreCase) ? 1 : 0);

    private static (string Folder, List<string> Files) Entries(IReadOnlyFileSystem fileSystem, string folder, out List<string> children)
    {
        var files = new List<string>();
        children = new List<string>();
        foreach (var entry in fileSystem.List(folder).Where(entry => !entry.IsSymbolicLink).OrderBy(entry => entry.Name, StringComparer.OrdinalIgnoreCase))
        {
            if (entry.IsDirectory)
            {
                children.Add(folder + "/" + entry.Name);
            }
            else
            {
                files.Add(entry.Name);
            }
        }

        return (folder, files);
    }

    private static byte[]? Read(IReadOnlyFileSystem fileSystem, string path)
    {
        if (fileSystem.Length(path) is not { } length || length <= 0 || length > MaximumSourceBytes)
        {
            return null;
        }

        using var stream = fileSystem.OpenRead(path);
        if (stream is null)
        {
            return null;
        }

        var buffer = new byte[length];
        var done = 0;
        while (done < buffer.Length)
        {
            var read = stream.Read(buffer, done, buffer.Length - done);
            if (read <= 0)
            {
                return null;
            }

            done += read;
        }

        return buffer;
    }
}

/// <summary>Downscales a cover with GDI+, which every Windows install carries: no imaging library is added to the companion.</summary>
public static class CoverImages
{
    private const int PixelFormat32bppArgb = 0x26200A;
    private const int HighQualityBicubic = 7;
    private static readonly Guid JpegEncoder = new("557CF401-1A04-11D3-9A73-0000F81EF32E");
    private static readonly Guid PngEncoder = new("557CF406-1A04-11D3-9A73-0000F81EF32E");
    private static readonly object Gate = new();
    private static IntPtr token;

    /// <summary>Null when the bytes are not an image GDI+ reads or the result would not fit the response.</summary>
    public static ScaledCover? Scale(byte[] source, int maximumWidth)
    {
        if (!OperatingSystem.IsWindows())
        {
            return null;
        }

        lock (Gate)
        {
            return ScaleWindows(source, maximumWidth);
        }
    }

    [SupportedOSPlatform("windows")]
    private static ScaledCover? ScaleWindows(byte[] source, int maximumWidth)
    {
        if (!Start())
        {
            return null;
        }

        var folder = Path.Combine(Path.GetTempPath(), "PanelDeControl.covers." + Guid.NewGuid().ToString("N"));
        IntPtr image = IntPtr.Zero, scaled = IntPtr.Zero, graphics = IntPtr.Zero;
        try
        {
            Directory.CreateDirectory(folder);
            var input = Path.Combine(folder, "source");
            File.WriteAllBytes(input, source);
            if (GdipLoadImageFromFile(input, out image) != 0 || GdipGetImageWidth(image, out var width) != 0 || GdipGetImageHeight(image, out var height) != 0
                || width == 0 || height == 0)
            {
                return null;
            }

            var png = source.Length > 8 && source[0] == 0x89 && source[1] == 0x50;
            var targetWidth = Math.Min(width, (uint)maximumWidth);
            var targetHeight = Math.Max(1u, (uint)Math.Round((double)height * targetWidth / width));
            if (GdipCreateBitmapFromScan0((int)targetWidth, (int)targetHeight, 0, PixelFormat32bppArgb, IntPtr.Zero, out scaled) != 0
                || GdipGetImageGraphicsContext(scaled, out graphics) != 0
                || GdipSetInterpolationMode(graphics, HighQualityBicubic) != 0
                || GdipDrawImageRectI(graphics, image, 0, 0, (int)targetWidth, (int)targetHeight) != 0)
            {
                return null;
            }

            var output = Path.Combine(folder, "scaled");
            var encoder = png ? PngEncoder : JpegEncoder;
            if (GdipSaveImageToFile(scaled, output, ref encoder, IntPtr.Zero) != 0)
            {
                return null;
            }

            var bytes = File.ReadAllBytes(output);
            return bytes.Length is > 0 and <= UpscalersWireCodec.MaximumCoverBytes
                ? new ScaledCover(bytes, png ? UpscalerCover.Png : UpscalerCover.Jpeg)
                : null;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DllNotFoundException or EntryPointNotFoundException)
        {
            return null;
        }
        finally
        {
            if (graphics != IntPtr.Zero)
            {
                GdipDeleteGraphics(graphics);
            }

            if (scaled != IntPtr.Zero)
            {
                GdipDisposeImage(scaled);
            }

            if (image != IntPtr.Zero)
            {
                GdipDisposeImage(image);
            }

            try
            {
                Directory.Delete(folder, true);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    [SupportedOSPlatform("windows")]
    private static bool Start()
    {
        if (token != IntPtr.Zero)
        {
            return true;
        }

        var input = new StartupInput { GdiplusVersion = 1 };
        return GdiplusStartup(out token, ref input, IntPtr.Zero) == 0;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct StartupInput
    {
        public uint GdiplusVersion;
        public IntPtr DebugEventCallback;
        [MarshalAs(UnmanagedType.Bool)]
        public bool SuppressBackgroundThread;
        [MarshalAs(UnmanagedType.Bool)]
        public bool SuppressExternalCodecs;
    }

    [DllImport("gdiplus.dll")]
    private static extern int GdiplusStartup(out IntPtr token, ref StartupInput input, IntPtr output);

    [DllImport("gdiplus.dll", CharSet = CharSet.Unicode)]
    private static extern int GdipLoadImageFromFile(string filename, out IntPtr image);

    [DllImport("gdiplus.dll")]
    private static extern int GdipGetImageWidth(IntPtr image, out uint width);

    [DllImport("gdiplus.dll")]
    private static extern int GdipGetImageHeight(IntPtr image, out uint height);

    [DllImport("gdiplus.dll")]
    private static extern int GdipCreateBitmapFromScan0(int width, int height, int stride, int format, IntPtr scan0, out IntPtr bitmap);

    [DllImport("gdiplus.dll")]
    private static extern int GdipGetImageGraphicsContext(IntPtr image, out IntPtr graphics);

    [DllImport("gdiplus.dll")]
    private static extern int GdipSetInterpolationMode(IntPtr graphics, int mode);

    [DllImport("gdiplus.dll")]
    private static extern int GdipDrawImageRectI(IntPtr graphics, IntPtr image, int x, int y, int width, int height);

    [DllImport("gdiplus.dll", CharSet = CharSet.Unicode)]
    private static extern int GdipSaveImageToFile(IntPtr image, string filename, ref Guid encoder, IntPtr parameters);

    [DllImport("gdiplus.dll")]
    private static extern int GdipDeleteGraphics(IntPtr graphics);

    [DllImport("gdiplus.dll")]
    private static extern int GdipDisposeImage(IntPtr image);
}
