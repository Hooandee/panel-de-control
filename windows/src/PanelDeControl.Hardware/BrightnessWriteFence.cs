namespace PanelDeControl.Hardware;

public sealed class BrightnessWriteInProgressException : InvalidOperationException
{
    public BrightnessWriteInProgressException()
        : base("A physical display brightness write is still active.")
    {
    }
}

public sealed class BrightnessWriteFence
{
    private readonly object syncRoot = new();
    private Task<uint>? activeWrite;

    public bool HasActiveWrite
    {
        get
        {
            lock (syncRoot)
            {
                return activeWrite is not null;
            }
        }
    }

    public uint Execute(Func<uint> write, TimeSpan timeout)
    {
        if (write is null)
        {
            throw new ArgumentNullException(nameof(write));
        }

        if (timeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout));
        }

        Task<uint> writeTask;
        lock (syncRoot)
        {
            if (activeWrite is not null)
            {
                throw new BrightnessWriteInProgressException();
            }

            writeTask = Task.Run(write);
            activeWrite = writeTask;
            _ = writeTask.ContinueWith(
                Complete,
                CancellationToken.None,
                TaskContinuationOptions.ExecuteSynchronously,
                TaskScheduler.Default);
        }

        return writeTask
            .WaitAsync(timeout)
            .GetAwaiter()
            .GetResult();
    }

    private void Complete(Task<uint> completedWrite)
    {
        if (completedWrite.IsFaulted)
        {
            _ = completedWrite.Exception;
        }

        lock (syncRoot)
        {
            if (ReferenceEquals(activeWrite, completedWrite))
            {
                activeWrite = null;
            }
        }
    }
}
