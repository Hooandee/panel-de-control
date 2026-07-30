using System.Runtime.Serialization;

namespace PanelDeControl.Core.Controls;

[DataContract]
public enum VolumeControlOperation
{
    [EnumMember]
    Get = 0,

    [EnumMember]
    Set = 1,
}

[DataContract]
public sealed class VolumeControlRequest
{
    private VolumeControlRequest()
    {
    }

    private VolumeControlRequest(
        VolumeControlOperation operation,
        double? requestedLevel)
    {
        Operation = operation;
        RequestedLevel = requestedLevel;
    }

    [DataMember(Name = "operation", Order = 1)]
    public VolumeControlOperation Operation { get; private set; }

    [DataMember(Name = "requested_level", Order = 2, EmitDefaultValue = false)]
    public double? RequestedLevel { get; private set; }

    public static VolumeControlRequest Get()
    {
        return new VolumeControlRequest(VolumeControlOperation.Get, null);
    }

    public static VolumeControlRequest Set(double requestedLevel)
    {
        if (!IsValidLevel(requestedLevel))
        {
            throw new ArgumentOutOfRangeException(nameof(requestedLevel));
        }

        return new VolumeControlRequest(VolumeControlOperation.Set, requestedLevel);
    }

    internal void Validate()
    {
        if (!Enum.IsDefined(typeof(VolumeControlOperation), Operation))
        {
            throw new InvalidDataException("Volume operation is invalid.");
        }

        if (Operation == VolumeControlOperation.Get && RequestedLevel.HasValue)
        {
            throw new InvalidDataException("A get request cannot include a requested level.");
        }

        if (Operation == VolumeControlOperation.Set &&
            (!RequestedLevel.HasValue || !IsValidLevel(RequestedLevel.Value)))
        {
            throw new InvalidDataException("A set request requires a level from zero to one.");
        }
    }

    private static bool IsValidLevel(double level)
    {
        return !double.IsNaN(level) &&
            !double.IsInfinity(level) &&
            level >= 0 &&
            level <= 1;
    }
}
