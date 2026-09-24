using System.Diagnostics;
using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

public sealed class AsusSensorSnapshotProvider : IHardwareSnapshotProvider
{
    private const string SupportedProfileId = "rog_xbox_ally_x";
    private const string SupportedBoardName = "RC73XA";
    private const string Source = "asus/atk-dsts";

    private static readonly Sensor[] Sensors =
    {
        new(AsusSensorRegister.CpuFan, "fan.cpu.rpm", "Fan 1", "RPM"),
        new(AsusSensorRegister.GpuFan, "fan.gpu.rpm", "Fan 2", "RPM"),
        new(AsusSensorRegister.CpuTemperature, "cpu.temperature", "CPU", "°C"),
        new(AsusSensorRegister.GpuTemperature, "gpu.temperature", "GPU", "°C"),
    };

    private readonly object gate = new();
    private readonly IClock clock;
    private readonly IHardwareSnapshotProvider local;
    private readonly TimeSpan asusTimeout;
    private readonly TimeSpan localTimeout;
    private readonly Probe<HardwareSnapshot> baseline;
    private readonly Probe<DeviceIdentity> identityProbe;
    private readonly Probe<uint?>[] probes;
    private DeviceIdentity? cachedIdentity;

    public AsusSensorSnapshotProvider(
        IHardwareSnapshotProvider local,
        IDeviceIdentityReader identity,
        IAsusSensorTransport transport,
        IClock clock,
        TimeSpan? asusTimeout = null,
        TimeSpan? localTimeout = null)
    {
        this.clock = clock;
        this.local = local;
        this.asusTimeout = asusTimeout ?? TimeSpan.FromMilliseconds(750);
        this.localTimeout = localTimeout ?? TimeSpan.FromSeconds(5);
        if (this.asusTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(asusTimeout));
        }

        if (this.localTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(localTimeout));
        }

        baseline = new Probe<HardwareSnapshot>(local.Capture, "lhm");
        identityProbe = new Probe<DeviceIdentity>(identity.Read, "identity");
        probes = Sensors
            .Select(sensor => new Probe<uint?>(() => transport.Read(sensor.Register), "asus"))
            .ToArray();
    }

    public HardwareSnapshot Capture()
    {
        lock (gate)
        {
            var started = Stopwatch.StartNew();
            var identity = ResolveIdentity(started);
            if (!IsSupported(identity))
            {
                return local.Capture();
            }

            baseline.Start();
            foreach (var probe in probes)
            {
                probe.Start();
            }

            var asusResults = probes
                .Select(probe => probe.Finish(Remaining(started, asusTimeout)))
                .ToArray();
            var localResult = baseline.Finish(Remaining(started, localTimeout));
            var snapshot = localResult.Value ?? MissingSnapshot(identity, localResult.Error!);
            var readings = snapshot.Readings.ToList();
            for (var index = 0; index < Sensors.Length; index++)
            {
                Merge(readings, Sensors[index], asusResults[index]);
            }

            return new HardwareSnapshot(clock.UtcNow, snapshot.DeviceModel, readings, snapshot.DeviceMaxWatts);
        }
    }

    private DeviceIdentity? ResolveIdentity(Stopwatch started)
    {
        if (cachedIdentity is not null)
        {
            return cachedIdentity;
        }

        var identity = identityProbe.CompletedValue;
        if (identity?.IsRecognized != true)
        {
            identityProbe.Start();
            identity = identityProbe.Finish(Remaining(started, asusTimeout)).Value;
        }

        if (identity?.IsRecognized == true)
        {
            cachedIdentity = identity;
        }

        return identity;
    }

    private static bool IsSupported(DeviceIdentity? identity)
    {
        return identity?.ProfileId == SupportedProfileId &&
            string.Equals(identity.BoardName, SupportedBoardName, StringComparison.OrdinalIgnoreCase);
    }

    private static void Merge(List<TelemetryReading> readings, Sensor sensor, Result<uint?> result)
    {
        var index = readings.FindIndex(reading => reading.Id == sensor.Id);
        if (index >= 0 && sensor.Kind == SensorKind.Temperature && HasPlausibleValue(readings[index]))
        {
            return;
        }

        var value = AsusAtkSensorTransport.Decode(sensor.Register, result.Value);
        var reading = value.HasValue
            ? TelemetryReading.Available(sensor.Id, sensor.Label, value.Value, sensor.Unit, Source)
            : TelemetryReading.Unavailable(
                sensor.Id,
                sensor.Label,
                sensor.Unit,
                ReadingStatus.Unavailable,
                result.Error ?? (result.Value.HasValue ? "sensor_implausible" : "asus_dsts_unavailable"));
        if (index >= 0)
        {
            readings[index] = reading;
        }
        else
        {
            readings.Add(reading);
        }
    }

    private static bool HasPlausibleValue(TelemetryReading reading)
    {
        return reading.Status == ReadingStatus.Available &&
            SensorPlausibility.IsPlausible(SensorKind.Temperature, reading.Value);
    }

    private static TimeSpan Remaining(Stopwatch started, TimeSpan budget)
    {
        var left = budget - started.Elapsed;
        return left > TimeSpan.Zero ? left : TimeSpan.Zero;
    }

    private HardwareSnapshot MissingSnapshot(DeviceIdentity? identity, string error)
    {
        var readings = new[] { "cpu.load", "gpu.load", "cpu.temperature", "gpu.temperature" }
            .Select(id => TelemetryReading.Unavailable(
                id,
                id.StartsWith("cpu", StringComparison.Ordinal) ? "CPU" : "GPU",
                id.EndsWith("load", StringComparison.Ordinal) ? "%" : "°C",
                ReadingStatus.Fault,
                error));
        return new HardwareSnapshot(
            clock.UtcNow,
            identity?.DisplayName ?? "Unknown device",
            readings,
            identity?.Profile?.Limits.TdpMaxCharger);
    }

    private sealed class Sensor
    {
        public Sensor(AsusSensorRegister register, string id, string label, string unit)
        {
            Register = register;
            Id = id;
            Label = label;
            Unit = unit;
        }

        public AsusSensorRegister Register { get; }

        public string Id { get; }

        public string Label { get; }

        public string Unit { get; }

        public SensorKind Kind => Unit == "RPM" ? SensorKind.Fan : SensorKind.Temperature;
    }

    private sealed class Result<T>
    {
        public Result(T? value, string? error)
        {
            Value = value;
            Error = error;
        }

        public T? Value { get; }

        public string? Error { get; }
    }

    private sealed class Probe<T>
    {
        private readonly Func<T> read;
        private readonly string name;
        private Task<Result<T>>? task;
        private bool busy;

        public Probe(Func<T> read, string name)
        {
            this.read = read;
            this.name = name;
        }

        public T? CompletedValue =>
            task is { IsCompletedSuccessfully: true } ? task.Result.Value : default;

        public void Start()
        {
            busy = task is { IsCompleted: false };
            if (busy)
            {
                return;
            }

            task = Task.Factory.StartNew(
                ReadSafely,
                CancellationToken.None,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default);
        }

        public Result<T> Finish(TimeSpan remaining)
        {
            if (busy)
            {
                return new Result<T>(default, name + "_probe_busy");
            }

            return task!.Wait(remaining)
                ? task.Result
                : new Result<T>(default, name + "_probe_timeout");
        }

        private Result<T> ReadSafely()
        {
            try
            {
                return new Result<T>(read(), null);
            }
            catch
            {
                return new Result<T>(default, name + "_probe_failed");
            }
        }
    }
}
