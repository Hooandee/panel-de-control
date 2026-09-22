using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Controls;

public static class TdpControlWireCodec
{
    private static readonly DataContractJsonSerializer RequestSerializer =
        new(typeof(TdpControlRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer =
        new(typeof(TdpControlResponse));

    public static string SerializeRequest(TdpControlRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }
        request.Validate();
        return Serialize(RequestSerializer, request);
    }

    public static TdpControlRequest DeserializeRequest(string payload)
    {
        try
        {
            var request = Deserialize<TdpControlRequest>(
                RequestSerializer,
                payload,
                "TDP request");
            request.Validate();
            return request;
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception exception)
        {
            throw new InvalidDataException("TDP request is malformed.", exception);
        }
    }

    public static string SerializeResponse(TdpControlResponse response)
    {
        if (response is null)
        {
            throw new ArgumentNullException(nameof(response));
        }
        response.Validate();
        return Serialize(ResponseSerializer, response);
    }

    public static TdpControlResponse DeserializeResponse(string payload)
    {
        try
        {
            var response = Deserialize<TdpControlResponse>(
                ResponseSerializer,
                payload,
                "TDP response");
            response.Validate();
            return response;
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception exception)
        {
            throw new InvalidDataException("TDP response is malformed.", exception);
        }
    }

    private static string Serialize(
        DataContractJsonSerializer serializer,
        object value)
    {
        using var stream = new MemoryStream();
        serializer.WriteObject(stream, value);
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static T Deserialize<T>(
        DataContractJsonSerializer serializer,
        string payload,
        string description)
        where T : class
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new InvalidDataException($"{description} must not be empty.");
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        return serializer.ReadObject(stream) as T
            ?? throw new InvalidDataException($"{description} is missing.");
    }
}
