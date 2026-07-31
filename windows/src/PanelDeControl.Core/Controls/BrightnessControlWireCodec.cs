using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Controls;

public static class BrightnessControlWireCodec
{
    private static readonly DataContractJsonSerializer RequestSerializer =
        new(typeof(BrightnessControlRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer =
        new(typeof(BrightnessControlResponse));

    public static string SerializeRequest(BrightnessControlRequest request)
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

    public static BrightnessControlRequest DeserializeRequest(string payload)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        var request = RequestSerializer.ReadObject(stream) as BrightnessControlRequest;
        if (request is null)
        {
            throw new InvalidDataException(
                "Brightness payload did not contain a request.");
        }

        request.Validate();
        return request;
    }

    public static string SerializeResponse(BrightnessControlResponse response)
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

    public static BrightnessControlResponse DeserializeResponse(string payload)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        var response = ResponseSerializer.ReadObject(stream) as BrightnessControlResponse;
        if (response is null)
        {
            throw new InvalidDataException(
                "Brightness payload did not contain a response.");
        }

        response.Validate();
        return response;
    }
}
