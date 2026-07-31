using System.Runtime.Serialization;

namespace PanelDeControl.Core.Controls;

[DataContract]
public enum BrightnessControlOperation
{
    [EnumMember]
    Get = 0,

    [EnumMember]
    Set = 1,
}

[DataContract]
public sealed class BrightnessControlRequest
{
    private BrightnessControlRequest()
    {
    }

    private BrightnessControlRequest(
        BrightnessControlOperation operation,
        int? requestedPercentage)
    {
        Operation = operation;
        RequestedPercentage = requestedPercentage;
    }

    [DataMember(Name = "operation", Order = 1, IsRequired = true)]
    public BrightnessControlOperation Operation { get; private set; }

    [DataMember(Name = "requested_percentage", Order = 2, EmitDefaultValue = false)]
    public int? RequestedPercentage { get; private set; }

    public static BrightnessControlRequest Get()
    {
        return new BrightnessControlRequest(BrightnessControlOperation.Get, null);
    }

    public static BrightnessControlRequest Set(int requestedPercentage)
    {
        return new BrightnessControlRequest(
            BrightnessControlOperation.Set,
            RequirePercentage(requestedPercentage, nameof(requestedPercentage)));
    }

    internal void Validate()
    {
        if (!Enum.IsDefined(typeof(BrightnessControlOperation), Operation))
        {
            throw new InvalidDataException("Brightness operation is invalid.");
        }

        if (Operation == BrightnessControlOperation.Get &&
            RequestedPercentage.HasValue)
        {
            throw new InvalidDataException(
                "A brightness get request cannot include a requested percentage.");
        }

        if (Operation == BrightnessControlOperation.Set &&
            (!RequestedPercentage.HasValue ||
            !IsPercentage(RequestedPercentage.Value)))
        {
            throw new InvalidDataException(
                "A brightness set request requires a percentage from zero to 100.");
        }
    }

    private static int RequirePercentage(int percentage, string parameterName)
    {
        if (!IsPercentage(percentage))
        {
            throw new ArgumentOutOfRangeException(parameterName);
        }

        return percentage;
    }

    private static bool IsPercentage(int percentage)
    {
        return percentage >= 0 && percentage <= 100;
    }
}
