using System.Diagnostics;
using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

public sealed class AsusSensorSnapshotProvider : IHardwareSnapshotProvider
{
    private static readonly Sensor[] Sensors =
    {
        new(AsusSensorRegister.CpuFan, "fan.cpu.rpm", "Ventilador 1", "RPM"),
        new(AsusSensorRegister.GpuFan, "fan.gpu.rpm", "Ventilador 2", "RPM"),
        new(AsusSensorRegister.CpuTemperature, "cpu.temperature", "CPU", "°C"),
        new(AsusSensorRegister.GpuTemperature, "gpu.temperature", "GPU", "°C"),
    };

    private readonly object gate = new();
    private readonly IClock clock;
    private readonly IHardwareSnapshotProvider local;
    private readonly TimeSpan timeout;
    private readonly Probe<HardwareSnapshot> baseline;
    private readonly Probe<DeviceIdentity> identityProbe;
    private readonly Probe<uint?>[] probes;
    private DeviceIdentity? cachedIdentity;

    public AsusSensorSnapshotProvider(IHardwareSnapshotProvider local, IDeviceIdentityReader identity,
        IAsusSensorTransport transport, IClock clock, TimeSpan? timeout = null)
    {
        this.clock = clock;
        this.local = local;
        this.timeout = timeout ?? TimeSpan.FromMilliseconds(750);
        if (this.timeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(timeout));
        baseline = new Probe<HardwareSnapshot>(local.Capture, "lhm");
        identityProbe = new Probe<DeviceIdentity>(identity.Read, "identity");
        probes = Sensors.Select(sensor => new Probe<uint?>(() => transport.Read(sensor.Register), "asus")).ToArray();
    }

    public HardwareSnapshot Capture()
    {
        lock (gate)
        {
            var watch = Stopwatch.StartNew();
            var identity = cachedIdentity;
            if (identity is null)
            {
                identity = identityProbe.CompletedValue;
                if (identity is null)
                {
                    identityProbe.Start();
                    identity = identityProbe.Finish(Remaining(watch)).Value;
                }
                if (identity?.IsRecognized == true) cachedIdentity = identity;
            }

            var supported = identity?.ProfileId == "rog_xbox_ally_x" &&
                string.Equals(identity.BoardName, "RC73XA", StringComparison.OrdinalIgnoreCase);
            if (!supported) return local.Capture();
            baseline.Start();
            foreach (var probe in probes) probe.Start();

            var localResult = baseline.Finish(Remaining(watch));
            var snapshot = localResult.Value ?? MissingSnapshot(identity, localResult.Error!);

            var readings = snapshot.Readings.ToList();
            for (var i = 0; i < Sensors.Length; i++)
            {
                var sensor = Sensors[i];
                var result = probes[i].Finish(Remaining(watch));
                var index = readings.FindIndex(reading => reading.Id == sensor.Id);
                if (index >= 0 && sensor.Unit == "°C" && readings[index].Status == ReadingStatus.Available &&
                    SensorPlausibility.IsPlausible(SensorKind.Temperature, readings[index].Value)) continue;

                var value = AsusAtkSensorTransport.Decode(sensor.Register, result.Value);
                var reading = value.HasValue
                    ? TelemetryReading.Available(sensor.Id, sensor.Label, value.Value, sensor.Unit, "asus/atk-dsts")
                    : TelemetryReading.Unavailable(sensor.Id, sensor.Label, sensor.Unit, ReadingStatus.Unavailable,
                        result.Error ?? (result.Value.HasValue ? "sensor_implausible" : "asus_dsts_unavailable"));
                if (index >= 0) readings[index] = reading;
                else readings.Add(reading);
            }

            return new HardwareSnapshot(clock.UtcNow, snapshot.DeviceModel, readings, snapshot.DeviceMaxWatts);
        }
    }

    private TimeSpan Remaining(Stopwatch watch) => timeout > watch.Elapsed ? timeout - watch.Elapsed : TimeSpan.Zero;

    private HardwareSnapshot MissingSnapshot(DeviceIdentity? identity, string error)
    {
        var readings = new[] { "cpu.load", "gpu.load", "cpu.temperature", "gpu.temperature" }
            .Select(id => TelemetryReading.Unavailable(id, id.StartsWith("cpu", StringComparison.Ordinal) ? "CPU" : "GPU",
                id.EndsWith("load", StringComparison.Ordinal) ? "%" : "°C", ReadingStatus.Fault, error));
        return new HardwareSnapshot(clock.UtcNow, identity?.DisplayName ?? "Unknown device", readings,
            identity?.Profile?.Limits.TdpMaxCharger);
    }

    private sealed record Sensor(AsusSensorRegister Register, string Id, string Label, string Unit);
    private sealed record Result<T>(T? Value, string? Error);

    private sealed class Probe<T>(Func<T> read, string name)
    {
        private Task<Result<T>>? task;
        private bool busy;

        public T? CompletedValue => task is { IsCompletedSuccessfully: true } ? task.Result.Value : default;

        public void Start()
        {
            busy = task is { IsCompleted: false };
            if (busy) return;
            task = Task.Factory.StartNew(() =>
            {
                try { return new Result<T>(read(), null); }
                catch { return new Result<T>(default, name + "_probe_failed"); }
            }, CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        }

        public Result<T> Finish(TimeSpan remaining)
        {
            if (busy) return new Result<T>(default, name + "_probe_busy");
            return task!.Wait(remaining) ? task.Result : new Result<T>(default, name + "_probe_timeout");
        }
    }
}
