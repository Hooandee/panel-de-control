using System.Runtime.InteropServices;
using PanelDeControl.Hardware;
using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class CoreAudioDeviceEnumeratorTests
{
    // companion.log on a ROG Xbox Ally X: the volume pipe made the enumerator first, and every game audio scan after
    // it failed with "Unable to cast object of type 'MMDeviceEnumeratorComObject' to type 'MMDeviceEnumeratorComObject'".
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

            using var scan = new CoreAudioGameMixer().Scan(new Dictionary<int, ProcessEntry>());
            Assert.NotNull(scan.Sessions);
        }
    }
}
