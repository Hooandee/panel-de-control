using System.Runtime.InteropServices;
using PanelDeControl.Hardware;
using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class CoreAudioDeviceEnumeratorTests
{
    // The volume pipe makes the enumerator first; every game audio scan after it used to fail with
    // "Unable to cast object of type 'MMDeviceEnumeratorComObject' to type 'MMDeviceEnumeratorComObject'".
    [Fact]
    public void GameAudioScanWorksAfterTheVolumeEndpointOpened()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        for (var round = 0; round < 2; round++)
        {
            try
            {
                using var endpoint = new CoreAudioEndpointVolumeProvider().OpenDefaultRenderEndpoint();
            }
            catch (COMException)
            {
                // A machine without an output device still made the enumerator.
            }

            try
            {
                using var scan = new CoreAudioGameMixer().Scan(new Dictionary<int, ProcessEntry>());
                Assert.NotNull(scan.Sessions);
            }
            catch (COMException)
            {
                // No audio service on this machine; the cast already succeeded.
            }
        }
    }
}
