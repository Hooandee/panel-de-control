namespace PanelDeControl.Hardware;

public sealed class BrightnessWriteInProgressException : InvalidOperationException
{
    public BrightnessWriteInProgressException()
        : base("A physical display brightness write is still active.")
    {
    }
}

public sealed class BrightnessReadInProgressException : InvalidOperationException
{
    public BrightnessReadInProgressException()
        : base("A physical display brightness read is still active.")
    {
    }
}

public sealed class BrightnessWriteFence
{
    private readonly object syncRoot = new();
    private Task? activeRead;
    private Task<uint>? activeWrite;

    public bool HasActiveRead
    {
        get
        {
            lock (syncRoot)
            {
                return activeRead is not null;
            }
        }
    }

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

    public T ExecuteRead<T>(Func<T> read, TimeSpan timeout)
    {
        if (read is null)
        {
            throw new ArgumentNullException(nameof(read));
        }

        if (timeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout));
        }

        Task<T> readTask;
        lock (syncRoot)
        {
            if (activeRead is not null)
            {
                throw new BrightnessReadInProgressException();
            }

            readTask = Task.Run(read);
            activeRead = readTask;
            _ = readTask.ContinueWith(
                CompleteRead,
                CancellationToken.None,
                TaskContinuationOptions.ExecuteSynchronously,
                TaskScheduler.Default);
        }

        return readTask
            .WaitAsync(timeout)
            .GetAwaiter()
            .GetResult();
    }

    private void CompleteRead(Task completedRead)
    {
        if (completedRead.IsFaulted)
        {
            _ = completedRead.Exception;
        }

        lock (syncRoot)
        {
            if (ReferenceEquals(activeRead, completedRead))
            {
                activeRead = null;
            }
        }
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
