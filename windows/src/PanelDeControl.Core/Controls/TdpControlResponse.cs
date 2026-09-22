using System.Runtime.Serialization;

namespace PanelDeControl.Core.Controls;

[DataContract]
public sealed class TdpControlResponse
{
    private int[] presetWatts = Array.Empty<int>();

    private TdpControlResponse()
    {
    }

    private TdpControlResponse(
        ControlStatus status,
        bool experimentalEnabled,
        int? requestedWatts,
        int? targetWatts,
        int? appliedWatts,
        int? minimumWatts,
        int? maximumWatts,
        IEnumerable<int>? presetWatts,
        bool? externalPower,
        bool readbackCandidateUnvalidated,
        bool manufacturerRecoveryUnverified,
        string? errorCode)
    {
        Status = status;
        ExperimentalEnabled = experimentalEnabled;
        RequestedWatts = requestedWatts;
        TargetWatts = targetWatts;
        AppliedWatts = appliedWatts;
        MinimumWatts = minimumWatts;
        MaximumWatts = maximumWatts;
        this.presetWatts = presetWatts?.ToArray() ?? Array.Empty<int>();
        ExternalPower = externalPower;
        ReadbackCandidateUnvalidated = readbackCandidateUnvalidated;
        ManufacturerRecoveryUnverified = manufacturerRecoveryUnverified;
        ErrorCode = errorCode;
        Validate();
    }

    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public ControlStatus Status { get; private set; }

    [DataMember(Name = "experimental_enabled", Order = 2, IsRequired = true)]
    public bool ExperimentalEnabled { get; private set; }

    [DataMember(Name = "requested_watts", Order = 3, EmitDefaultValue = false)]
    public int? RequestedWatts { get; private set; }

    [DataMember(Name = "target_watts", Order = 4, EmitDefaultValue = false)]
    public int? TargetWatts { get; private set; }

    [DataMember(Name = "applied_watts", Order = 5, EmitDefaultValue = false)]
    public int? AppliedWatts { get; private set; }

    [DataMember(Name = "minimum_watts", Order = 6, EmitDefaultValue = false)]
    public int? MinimumWatts { get; private set; }

    [DataMember(Name = "maximum_watts", Order = 7, EmitDefaultValue = false)]
    public int? MaximumWatts { get; private set; }

    public IReadOnlyList<int> PresetWatts => presetWatts;

    [DataMember(Name = "preset_watts", Order = 8, IsRequired = true)]
    private int[] PresetWattsWire
    {
        get => presetWatts;
        set => presetWatts = value ?? Array.Empty<int>();
    }

    [DataMember(Name = "external_power", Order = 9, EmitDefaultValue = false)]
    public bool? ExternalPower { get; private set; }

    [DataMember(
        Name = "readback_candidate_unvalidated",
        Order = 10,
        IsRequired = true)]
    public bool ReadbackCandidateUnvalidated { get; private set; }

    [DataMember(
        Name = "manufacturer_recovery_unverified",
        Order = 11,
        IsRequired = true)]
    public bool ManufacturerRecoveryUnverified { get; private set; }

    [DataMember(Name = "error_code", Order = 12, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }

    public static TdpControlResponse Available(
        bool experimentalEnabled,
        int minimumWatts,
        int maximumWatts,
        IEnumerable<int> presetWatts,
        bool externalPower,
        bool manufacturerRecoveryUnverified = false)
    {
        return new TdpControlResponse(
            ControlStatus.Available,
            experimentalEnabled,
            null,
            null,
            null,
            minimumWatts,
            maximumWatts,
            presetWatts,
            externalPower,
            true,
            manufacturerRecoveryUnverified,
            null);
    }

    public static TdpControlResponse Applied(
        bool experimentalEnabled,
        int requestedWatts,
        int targetWatts,
        int appliedWatts,
        int minimumWatts,
        int maximumWatts,
        IEnumerable<int> presetWatts,
        bool externalPower)
    {
        if (targetWatts != appliedWatts)
        {
            throw new ArgumentException(
                "Applied watts must match the clamped target.",
                nameof(appliedWatts));
        }

        return new TdpControlResponse(
            ControlStatus.Applied,
            experimentalEnabled,
            requestedWatts,
            targetWatts,
            appliedWatts,
            minimumWatts,
            maximumWatts,
            presetWatts,
            externalPower,
            true,
            false,
            null);
    }

    public static TdpControlResponse Rejected(
        bool experimentalEnabled,
        int? requestedWatts,
        int? targetWatts,
        int minimumWatts,
        int maximumWatts,
        IEnumerable<int> presetWatts,
        bool? externalPower,
        string errorCode)
    {
        return FailedAttempt(
            ControlStatus.Rejected,
            experimentalEnabled,
            requestedWatts,
            targetWatts,
            minimumWatts,
            maximumWatts,
            presetWatts,
            externalPower,
            errorCode);
    }

    public static TdpControlResponse Rejected(
        bool experimentalEnabled,
        string errorCode)
    {
        return new TdpControlResponse(
            ControlStatus.Rejected,
            experimentalEnabled,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            false,
            false,
            RequireText(errorCode, nameof(errorCode)));
    }

    public static TdpControlResponse Unverifiable(
        bool experimentalEnabled,
        int requestedWatts,
        int targetWatts,
        int minimumWatts,
        int maximumWatts,
        IEnumerable<int> presetWatts,
        bool externalPower,
        string errorCode)
    {
        return FailedAttempt(
            ControlStatus.Unverifiable,
            experimentalEnabled,
            requestedWatts,
            targetWatts,
            minimumWatts,
            maximumWatts,
            presetWatts,
            externalPower,
            errorCode);
    }

    public static TdpControlResponse Indeterminate(
        bool experimentalEnabled,
        int requestedWatts,
        string errorCode)
    {
        return new TdpControlResponse(
            ControlStatus.Unverifiable,
            experimentalEnabled,
            requestedWatts,
            null,
            null,
            null,
            null,
            null,
            null,
            false,
            false,
            RequireText(errorCode, nameof(errorCode)));
    }

    public static TdpControlResponse Unavailable(
        bool experimentalEnabled,
        string errorCode)
    {
        return TerminalFailure(
            ControlStatus.Unavailable,
            experimentalEnabled,
            errorCode);
    }

    public static TdpControlResponse Fault(
        bool experimentalEnabled,
        string errorCode)
    {
        return TerminalFailure(
            ControlStatus.Fault,
            experimentalEnabled,
            errorCode);
    }

    internal void Validate()
    {
        if (!Enum.IsDefined(typeof(ControlStatus), Status))
        {
            throw new InvalidDataException("TDP control status is invalid.");
        }

        if (MinimumWatts.HasValue != MaximumWatts.HasValue)
        {
            throw new InvalidDataException("TDP limits must be provided together.");
        }

        if (MinimumWatts.HasValue &&
            (MinimumWatts.Value < 0 ||
             MaximumWatts!.Value < MinimumWatts.Value))
        {
            throw new InvalidDataException("TDP limits are invalid.");
        }

        if (AppliedWatts.HasValue &&
            (!TargetWatts.HasValue || AppliedWatts.Value != TargetWatts.Value))
        {
            throw new InvalidDataException(
                "Applied TDP must match the clamped target.");
        }

        var isFailure = Status is ControlStatus.Unavailable or
            ControlStatus.Rejected or
            ControlStatus.Unverifiable or
            ControlStatus.Fault;
        if (isFailure == string.IsNullOrWhiteSpace(ErrorCode))
        {
            throw new InvalidDataException("TDP error state is inconsistent.");
        }

        if (Status == ControlStatus.Available &&
            (RequestedWatts.HasValue ||
             TargetWatts.HasValue ||
             AppliedWatts.HasValue))
        {
            throw new InvalidDataException(
                "Available TDP state cannot describe a write attempt.");
        }

        if (Status == ControlStatus.Applied &&
            (!RequestedWatts.HasValue ||
             !TargetWatts.HasValue ||
             !AppliedWatts.HasValue))
        {
            throw new InvalidDataException(
                "Applied TDP requires requested, target, and applied watts.");
        }

        if (Status == ControlStatus.Unverifiable &&
            (!RequestedWatts.HasValue || AppliedWatts.HasValue))
        {
            throw new InvalidDataException(
                "Unverifiable TDP requires an unapplied write request.");
        }

        if (Status is ControlStatus.Unavailable or ControlStatus.Fault &&
            (RequestedWatts.HasValue ||
             TargetWatts.HasValue ||
             AppliedWatts.HasValue ||
             MinimumWatts.HasValue ||
             MaximumWatts.HasValue ||
             presetWatts.Length > 0 ||
             ExternalPower.HasValue))
        {
            throw new InvalidDataException(
                "Terminal TDP failures cannot invent capabilities.");
        }
    }

    private static TdpControlResponse FailedAttempt(
        ControlStatus status,
        bool experimentalEnabled,
        int? requestedWatts,
        int? targetWatts,
        int minimumWatts,
        int maximumWatts,
        IEnumerable<int> presetWatts,
        bool? externalPower,
        string errorCode)
    {
        return new TdpControlResponse(
            status,
            experimentalEnabled,
            requestedWatts,
            targetWatts,
            null,
            minimumWatts,
            maximumWatts,
            presetWatts,
            externalPower,
            true,
            false,
            RequireText(errorCode, nameof(errorCode)));
    }

    private static TdpControlResponse TerminalFailure(
        ControlStatus status,
        bool experimentalEnabled,
        string errorCode)
    {
        return new TdpControlResponse(
            status,
            experimentalEnabled,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            false,
            false,
            RequireText(errorCode, nameof(errorCode)));
    }

    private static string RequireText(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Value must not be empty.", parameterName);
        }

        return value;
    }
}
