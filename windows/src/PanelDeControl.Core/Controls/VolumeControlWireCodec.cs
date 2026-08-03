using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Controls;

public static class VolumeControlWireCodec
{
    private static readonly DataContractJsonSerializer RequestSerializer =
        new(typeof(VolumeControlRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer =
        new(typeof(VolumeControlResponse));

    public static string SerializeRequest(VolumeControlRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        request.Validate();
        using var stream = new MemoryStream();
        RequestSerializer.WriteObject(stream, request);
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    public static VolumeControlRequest DeserializeRequest(string payload)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        var request = RequestSerializer.ReadObject(stream) as VolumeControlRequest;
        if (request is null)
        {
            throw new InvalidDataException("Control payload did not contain a request.");
        }

        request.Validate();
        return request;
    }

    public static string SerializeResponse(VolumeControlResponse response)
    {
        if (response is null)
        {
            throw new ArgumentNullException(nameof(response));
        }

        response.Validate();
        using var stream = new MemoryStream();
        ResponseSerializer.WriteObject(stream, response);
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    public static VolumeControlResponse DeserializeResponse(string payload)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        var response = ResponseSerializer.ReadObject(stream) as VolumeControlResponse;
        if (response is null)
        {
            throw new InvalidDataException("Control payload did not contain a response.");
        }

        response.Validate();
        return response;
    }
}
