using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Themes;
using PanelDeControl.Hardware.Themes;

namespace PanelDeControl.Hardware;

public interface IThemesController
{
    Task<ThemesResponse> HandleAsync(ThemesRequest request, CancellationToken cancellationToken);
}

public sealed class ThemesController : IThemesController
{
    private static readonly TimeSpan ReadbackTimeout = TimeSpan.FromSeconds(8);
    private static readonly TimeSpan LongOperationTimeout = TimeSpan.FromSeconds(90);

    private readonly ThemeService service;
    private readonly SteamThemeEngine engine;

    public ThemesController(ThemeService service, SteamThemeEngine engine)
    {
        this.service = service;
        this.engine = engine;
    }

    public async Task<ThemesResponse> HandleAsync(ThemesRequest request, CancellationToken cancellationToken)
    {
        try
        {
            switch (request.Operation)
            {
                case ThemesOperation.Get:
                    _ = Task.Run(() => service.RefreshCatalogAsync(force: false, CancellationToken.None), CancellationToken.None);
                    return Response(engine.Status);
                case ThemesOperation.RefreshCatalog:
                    await service.RefreshCatalogAsync(force: true, cancellationToken).ConfigureAwait(false);
                    return Response(engine.Status);
                case ThemesOperation.Install:
                    using (var timeout = Timeout(cancellationToken, LongOperationTimeout))
                    {
                        await service.InstallAsync(request.CatalogId!, request.Version!, timeout.Token).ConfigureAwait(false);
                    }

                    return await ReadbackAsync(cancellationToken).ConfigureAwait(false);
                case ThemesOperation.SetEnabled:
                    service.SetEnabled(request.Name!, request.Enabled!.Value);
                    return await ReadbackAsync(cancellationToken).ConfigureAwait(false);
                case ThemesOperation.SetOption:
                    service.SetPatch(request.Name!, request.Option!, request.Value!);
                    return await ReadbackAsync(cancellationToken).ConfigureAwait(false);
                case ThemesOperation.EnableSteamDebugging:
                    service.EnableSteamDebugging();
                    return await ReadbackAsync(cancellationToken).ConfigureAwait(false);
                case ThemesOperation.RestartSteam:
                    using (var timeout = Timeout(cancellationToken, LongOperationTimeout))
                    {
                        await service.RestartSteamAsync(timeout.Token).ConfigureAwait(false);
                    }

                    return await ReadbackAsync(cancellationToken).ConfigureAwait(false);
                default:
                    return Response(engine.Status, ThemesResponseStatus.Rejected, "unsupported_operation");
            }
        }
        catch (ThemeInstallException exception)
        {
            CompanionLog.Write($"themes.{request.Operation}", exception);
            return Response(engine.Status, ThemesResponseStatus.Rejected, exception.Code);
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            CompanionLog.Write($"themes.{request.Operation}", exception);
            return Response(engine.Status, ThemesResponseStatus.Fault, exception switch
            {
                OperationCanceledException or TimeoutException => "themes_timeout",
                UnauthorizedAccessException or IOException => "themes_storage_failed",
                System.Net.Http.HttpRequestException => "catalog_unavailable",
                _ => "themes_failed",
            });
        }
    }

    private async Task<ThemesResponse> ReadbackAsync(CancellationToken cancellationToken)
    {
        using var timeout = Timeout(cancellationToken, ReadbackTimeout);
        try
        {
            return Response(await engine.InvalidateAsync(timeout.Token).ConfigureAwait(false));
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return Response(engine.Status);
        }
    }

    private ThemesResponse Response(ThemeEngineStatus status, ThemesResponseStatus result = ThemesResponseStatus.Ok, string? errorCode = null) =>
        ThemesResponseBuilder.Build(service.Catalog, service.Library(), service.Settings(), status, result, errorCode);

    private static CancellationTokenSource Timeout(CancellationToken cancellationToken, TimeSpan timeout)
    {
        var source = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        source.CancelAfter(timeout);
        return source;
    }
}

/// <summary>
/// <c>LOCAL\PanelDeControl.Themes</c>: one request line in, one response line out.
/// </summary>
public sealed class ThemesPipeServer
{
    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Themes";

    private readonly string pipeName;
    private readonly IThemesController controller;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;

    public ThemesPipeServer(string pipeName, IThemesController controller, Func<string, NamedPipeServerStream> pipeFactory)
    {
        this.pipeName = pipeName;
        this.controller = controller;
        this.pipeFactory = pipeFactory;
    }

    public async Task RunUntilCancelledAsync(CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                await RunOnceAsync(cancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        await using var server = await PipeInstances.CreateAsync(pipeFactory, pipeName, cancellationToken).ConfigureAwait(false);
        using var clientRelease = PipeClientRelease.For(server);
        await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);
        using var reader = new StreamReader(server, new UTF8Encoding(false), false, 1024, leaveOpen: true);
        var writer = new StreamWriter(server, new UTF8Encoding(false), 4096, leaveOpen: true) { AutoFlush = true };
        try
        {
            using var requestTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            requestTimeout.CancelAfter(TimeSpan.FromSeconds(1));
            string? payload;
            try
            {
                payload = await ReadLineAsync(reader, requestTimeout.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                return;
            }

            if (payload is null)
            {
                return;
            }

            ThemesResponse response;
            try
            {
                var request = ThemesWireCodec.DeserializeRequest(payload);
                response = await controller.HandleAsync(request, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is InvalidDataException or ArgumentException or System.Runtime.Serialization.SerializationException)
            {
                response = new ThemesResponse { Status = ThemesResponseStatus.Rejected, ErrorCode = "invalid_themes_request" };
            }

            try
            {
                await writer.WriteLineAsync(ThemesWireCodec.SerializeResponse(response)).ConfigureAwait(false);
            }
            catch (IOException)
            {
            }
        }
        finally
        {
            try
            {
                await writer.DisposeAsync().ConfigureAwait(false);
            }
            catch (IOException)
            {
            }
            catch (ObjectDisposedException)
            {
            }
        }
    }

    private static async Task<string?> ReadLineAsync(StreamReader reader, CancellationToken cancellationToken)
    {
        var line = new StringBuilder();
        var character = new char[1];
        while (true)
        {
            if (await reader.ReadAsync(character.AsMemory(0, 1), cancellationToken).ConfigureAwait(false) == 0)
            {
                return null;
            }

            if (character[0] == '\n')
            {
                return line.ToString();
            }

            if (character[0] != '\r')
            {
                if (line.Length == ThemesWireCodec.MaximumRequestLength)
                {
                    return null;
                }

                line.Append(character[0]);
            }
        }
    }
}
