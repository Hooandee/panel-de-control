using System.Runtime.Serialization;

namespace PanelDeControl.Core.Controls;

[DataContract]
public sealed class BrightnessControlResponse
{
    private BrightnessControlResponse()
    {
    }

    private BrightnessControlResponse(
        ControlStatus status,
        int? requestedPercentage,
        int? observedPercentage,
        string? errorCode)
    {
        Status = status;
        RequestedPercentage = requestedPercentage;
        ObservedPercentage = observedPercentage;
        ErrorCode = errorCode;
    }

    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public ControlStatus Status { get; private set; }

    [DataMember(Name = "requested_percentage", Order = 2, EmitDefaultValue = false)]
    public int? RequestedPercentage { get; private set; }

    [DataMember(Name = "observed_percentage", Order = 3, EmitDefaultValue = false)]
    public int? ObservedPercentage { get; private set; }

    [DataMember(Name = "error_code", Order = 4, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }

    public static BrightnessControlResponse Available(int observedPercentage)
    {
        return new BrightnessControlResponse(
            ControlStatus.Available,
            null,
            RequirePercentage(observedPercentage, nameof(observedPercentage)),
            null);
    }

    public static BrightnessControlResponse Applied(
        int requestedPercentage,
        int observedPercentage)
    {
        return new BrightnessControlResponse(
            ControlStatus.Applied,
            RequirePercentage(requestedPercentage, nameof(requestedPercentage)),
            RequirePercentage(observedPercentage, nameof(observedPercentage)),
            null);
    }

    public static BrightnessControlResponse Unavailable(string errorCode)
    {
        return Failure(ControlStatus.Unavailable, errorCode);
    }

    public static BrightnessControlResponse PermissionRequired(string errorCode)
    {
        return Failure(ControlStatus.PermissionRequired, errorCode);
    }

    public static BrightnessControlResponse Rejected(string errorCode)
    {
        return Failure(ControlStatus.Rejected, errorCode);
    }

    public static BrightnessControlResponse Unverifiable(
        int requestedPercentage,
        int? observedPercentage,
        string errorCode)
    {
        return new BrightnessControlResponse(
            ControlStatus.Unverifiable,
            RequirePercentage(requestedPercentage, nameof(requestedPercentage)),
            observedPercentage.HasValue
                ? RequirePercentage(
                    observedPercentage.Value,
                    nameof(observedPercentage))
                : null,
            RequireText(errorCode, nameof(errorCode)));
    }

    public static BrightnessControlResponse Fault(string errorCode)
    {
        return Failure(ControlStatus.Fault, errorCode);
    }

    internal void Validate()
    {
        if (!Enum.IsDefined(typeof(ControlStatus), Status))
        {
            throw new InvalidDataException("Brightness control status is invalid.");
        }

        switch (Status)
        {
            case ControlStatus.Available:
                RequireNoRequestedPercentage();
                RequireObservedPercentage();
                RequireNoError();
                break;
            case ControlStatus.Applied:
                RequireRequestedPercentage();
                RequireObservedPercentage();
                RequireNoError();
                break;
            case ControlStatus.Unavailable:
            case ControlStatus.PermissionRequired:
            case ControlStatus.Rejected:
            case ControlStatus.Fault:
                RequireNoRequestedPercentage();
                RequireNoObservedPercentage();
                RequireError();
                break;
            case ControlStatus.Unverifiable:
                RequireRequestedPercentage();
                if (ObservedPercentage.HasValue)
                {
                    RequirePercentage(
                        ObservedPercentage.Value,
                        nameof(ObservedPercentage));
                }

                RequireError();
                break;
            default:
                throw new InvalidDataException(
                    "Brightness control status is unsupported.");
        }
    }

    private static BrightnessControlResponse Failure(
        ControlStatus status,
        string errorCode)
    {
        return new BrightnessControlResponse(
            status,
            null,
            null,
            RequireText(errorCode, nameof(errorCode)));
    }

    private void RequireRequestedPercentage()
    {
        if (!RequestedPercentage.HasValue)
        {
            throw new InvalidDataException(
                "Requested brightness percentage is missing.");
        }

        RequirePercentage(RequestedPercentage.Value, nameof(RequestedPercentage));
    }

    private void RequireObservedPercentage()
    {
        if (!ObservedPercentage.HasValue)
        {
            throw new InvalidDataException(
                "Observed brightness percentage is missing.");
        }

        RequirePercentage(ObservedPercentage.Value, nameof(ObservedPercentage));
    }

    private void RequireNoRequestedPercentage()
    {
        if (RequestedPercentage.HasValue)
        {
            throw new InvalidDataException(
                "Unexpected requested brightness percentage.");
        }
    }

    private void RequireNoObservedPercentage()
    {
        if (ObservedPercentage.HasValue)
        {
            throw new InvalidDataException(
                "Unexpected observed brightness percentage.");
        }
    }

    private void RequireError()
    {
        if (string.IsNullOrWhiteSpace(ErrorCode))
        {
            throw new InvalidDataException("Brightness error code is missing.");
        }
    }

    private void RequireNoError()
    {
        if (!string.IsNullOrWhiteSpace(ErrorCode))
        {
            throw new InvalidDataException("Unexpected brightness error code.");
        }
    }

    private static int RequirePercentage(int percentage, string parameterName)
    {
        if (percentage < 0 || percentage > 100)
        {
            throw new ArgumentOutOfRangeException(parameterName);
        }

        return percentage;
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
