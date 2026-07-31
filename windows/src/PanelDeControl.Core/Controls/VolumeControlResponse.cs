using System.Runtime.Serialization;

namespace PanelDeControl.Core.Controls;

[DataContract]
public sealed class VolumeControlResponse
{
    private VolumeControlResponse()
    {
    }

    private VolumeControlResponse(
        ControlStatus status,
        double? requestedLevel,
        double? observedLevel,
        bool? requestedMuted,
        bool? observedMuted,
        string? errorCode)
    {
        Status = status;
        RequestedLevel = requestedLevel;
        ObservedLevel = observedLevel;
        RequestedMuted = requestedMuted;
        ObservedMuted = observedMuted;
        ErrorCode = errorCode;
    }

    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public ControlStatus Status { get; private set; }

    [DataMember(Name = "requested_level", Order = 2, EmitDefaultValue = false)]
    public double? RequestedLevel { get; private set; }

    [DataMember(Name = "observed_level", Order = 3, EmitDefaultValue = false)]
    public double? ObservedLevel { get; private set; }

    [DataMember(Name = "requested_muted", Order = 4, EmitDefaultValue = false)]
    public bool? RequestedMuted { get; private set; }

    [DataMember(Name = "observed_muted", Order = 5, EmitDefaultValue = false)]
    public bool? ObservedMuted { get; private set; }

    [DataMember(Name = "error_code", Order = 6, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }

    public static VolumeControlResponse Applied(
        double requestedLevel,
        double observedLevel)
    {
        return new VolumeControlResponse(
            ControlStatus.Applied,
            RequireLevel(requestedLevel, nameof(requestedLevel)),
            RequireLevel(observedLevel, nameof(observedLevel)),
            null,
            null,
            null);
    }

    public static VolumeControlResponse Available(
        double observedLevel,
        bool observedMuted)
    {
        return new VolumeControlResponse(
            ControlStatus.Available,
            null,
            RequireLevel(observedLevel, nameof(observedLevel)),
            null,
            observedMuted,
            null);
    }

    public static VolumeControlResponse Unavailable(string errorCode)
    {
        return Failure(ControlStatus.Unavailable, errorCode);
    }

    public static VolumeControlResponse PermissionRequired(string errorCode)
    {
        return Failure(ControlStatus.PermissionRequired, errorCode);
    }

    public static VolumeControlResponse Rejected(string errorCode)
    {
        return Failure(ControlStatus.Rejected, errorCode);
    }

    public static VolumeControlResponse Unverifiable(
        double requestedLevel,
        double? observedLevel,
        string errorCode)
    {
        return new VolumeControlResponse(
            ControlStatus.Unverifiable,
            RequireLevel(requestedLevel, nameof(requestedLevel)),
            observedLevel.HasValue
                ? RequireLevel(observedLevel.Value, nameof(observedLevel))
                : null,
            null,
            null,
            RequireText(errorCode, nameof(errorCode)));
    }

    public static VolumeControlResponse MuteApplied(
        bool requestedMuted,
        bool observedMuted)
    {
        return new VolumeControlResponse(
            ControlStatus.Applied,
            null,
            null,
            requestedMuted,
            observedMuted,
            null);
    }

    public static VolumeControlResponse MuteUnverifiable(
        bool requestedMuted,
        bool? observedMuted,
        string errorCode)
    {
        return new VolumeControlResponse(
            ControlStatus.Unverifiable,
            null,
            null,
            requestedMuted,
            observedMuted,
            RequireText(errorCode, nameof(errorCode)));
    }

    public static VolumeControlResponse Fault(string errorCode)
    {
        return Failure(ControlStatus.Fault, errorCode);
    }

    internal void Validate()
    {
        if (!Enum.IsDefined(typeof(ControlStatus), Status))
        {
            throw new InvalidDataException("Volume control status is invalid.");
        }

        switch (Status)
        {
            case ControlStatus.Available:
                RequireNoRequestedLevel();
                RequireObservedLevel();
                RequireNoRequestedMuted();
                RequireObservedMuted();
                RequireNoError();
                break;
            case ControlStatus.Applied:
                RequireAppliedValues();
                RequireNoError();
                break;
            case ControlStatus.Unavailable:
            case ControlStatus.PermissionRequired:
            case ControlStatus.Rejected:
            case ControlStatus.Fault:
                RequireNoRequestedLevel();
                RequireNoObservedLevel();
                RequireNoMuted();
                RequireError();
                break;
            case ControlStatus.Unverifiable:
                RequireUnverifiableValues();
                RequireError();
                break;
        }
    }

    private static VolumeControlResponse Failure(
        ControlStatus status,
        string errorCode)
    {
        return new VolumeControlResponse(
            status,
            null,
            null,
            null,
            null,
            RequireText(errorCode, nameof(errorCode)));
    }

    private void RequireAppliedValues()
    {
        if (RequestedLevel.HasValue)
        {
            RequireRequestedLevel();
            RequireObservedLevel();
            RequireNoMuted();
            return;
        }

        RequireNoLevels();
        RequireRequestedMuted();
        RequireObservedMuted();
    }

    private void RequireUnverifiableValues()
    {
        if (RequestedLevel.HasValue)
        {
            RequireRequestedLevel();
            if (ObservedLevel.HasValue)
            {
                RequireLevel(ObservedLevel.Value, nameof(ObservedLevel));
            }

            RequireNoMuted();
            return;
        }

        RequireNoLevels();
        RequireRequestedMuted();
    }

    private void RequireRequestedLevel()
    {
        if (!RequestedLevel.HasValue)
        {
            throw new InvalidDataException("Requested volume level is missing.");
        }

        RequireLevel(RequestedLevel.Value, nameof(RequestedLevel));
    }

    private void RequireObservedLevel()
    {
        if (!ObservedLevel.HasValue)
        {
            throw new InvalidDataException("Observed volume level is missing.");
        }

        RequireLevel(ObservedLevel.Value, nameof(ObservedLevel));
    }

    private void RequireNoRequestedLevel()
    {
        if (RequestedLevel.HasValue)
        {
            throw new InvalidDataException("Unexpected requested volume level.");
        }
    }

    private void RequireNoObservedLevel()
    {
        if (ObservedLevel.HasValue)
        {
            throw new InvalidDataException("Unexpected observed volume level.");
        }
    }

    private void RequireNoLevels()
    {
        RequireNoRequestedLevel();
        RequireNoObservedLevel();
    }

    private void RequireRequestedMuted()
    {
        if (!RequestedMuted.HasValue)
        {
            throw new InvalidDataException("Requested mute state is missing.");
        }
    }

    private void RequireObservedMuted()
    {
        if (!ObservedMuted.HasValue)
        {
            throw new InvalidDataException("Observed mute state is missing.");
        }
    }

    private void RequireNoRequestedMuted()
    {
        if (RequestedMuted.HasValue)
        {
            throw new InvalidDataException("Unexpected requested mute state.");
        }
    }

    private void RequireNoMuted()
    {
        if (RequestedMuted.HasValue || ObservedMuted.HasValue)
        {
            throw new InvalidDataException("Unexpected mute state.");
        }
    }

    private void RequireError()
    {
        if (string.IsNullOrWhiteSpace(ErrorCode))
        {
            throw new InvalidDataException("Volume error code is missing.");
        }
    }

    private void RequireNoError()
    {
        if (!string.IsNullOrWhiteSpace(ErrorCode))
        {
            throw new InvalidDataException("Unexpected volume error code.");
        }
    }

    private static double RequireLevel(double level, string parameterName)
    {
        if (double.IsNaN(level) ||
            double.IsInfinity(level) ||
            level < 0 ||
            level > 1)
        {
            throw new ArgumentOutOfRangeException(parameterName);
        }

        return level;
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
