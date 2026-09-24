using System.Runtime.CompilerServices;

namespace PanelDeControl.Service.Tests;

internal static class TestHostSetup
{
    // Pipe and fence tests wait on short real-time deadlines; a cold thread pool on small CI
    // runners delays their continuations past those deadlines.
    [ModuleInitializer]
    internal static void WarmThreadPool()
    {
        ThreadPool.GetMinThreads(out var workers, out var completionPorts);
        ThreadPool.SetMinThreads(Math.Max(workers, 32), Math.Max(completionPorts, 32));
    }
}
