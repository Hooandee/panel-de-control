#include "face_probe.h"
#include <shcore.h>
#include <shlwapi.h>
#undef GetCurrentTime
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Foundation.Numerics.h>
#include <winrt/Windows.Storage.Streams.h>
#include <winrt/Windows.UI.Composition.h>
#include <winrt/Windows.UI.Core.h>
#include <winrt/Windows.UI.Xaml.h>
#include <winrt/Windows.UI.Xaml.Controls.h>
#include <winrt/Windows.UI.Xaml.Hosting.h>
#include <winrt/Windows.UI.Xaml.Media.h>
#include <atomic>
#include <chrono>

namespace keyboard {
namespace {
using namespace winrt;
using namespace Windows::UI;
using namespace Windows::UI::Xaml;
using namespace Windows::UI::Xaml::Controls;
using namespace Windows::UI::Xaml::Media;
using namespace Windows::UI::Composition;

struct FaceProbe {
    std::atomic<bool> begun{false};
    std::atomic<bool> selected{false};
    std::atomic<std::uint32_t> flags{0};
    std::atomic<HRESULT> result{S_OK};
    Grid parent{nullptr};
    Canvas decoration{nullptr};
    LoadedImageSurface surface{nullptr};
    DispatcherTimer timer{nullptr};
    event_token loaded{}, tick{}, resized{};
    bool finished = false;
    bool stopping = false;
    bool cleanupRunning = false;
    unsigned cleanupAttempts = 0;

    template<class Action> bool Attempt(Action action) noexcept {
        try { action(); return true; }
        catch (...) { result = to_hresult(); flags.fetch_or(ProbeFailed); return false; }
    }

    void Remove() noexcept {
        if (finished || cleanupRunning) return;
        cleanupRunning = true;
        stopping = true;
        ++cleanupAttempts;
        const bool absent = Attempt([&] {
            if (!parent || !decoration) return;
            std::uint32_t index = 0;
            auto children = parent.Children();
            if (children.IndexOf(decoration, index)) children.RemoveAt(index);
            if (children.IndexOf(decoration, index)) throw hresult_error(E_FAIL);
        });
        Attempt([&] {
            if (decoration) Hosting::ElementCompositionPreview::SetElementChildVisual(decoration, nullptr);
        });
        if (!absent && cleanupAttempts < 3) {
            Attempt([&] { if (timer) timer.Interval(std::chrono::seconds(1)); });
            cleanupRunning = false;
            return;
        }
        finished = absent;
        if (absent) flags.fetch_or(ProbeRestored);
        // Independent revocation failures must not prevent removal of our visual.
        Attempt([&] { if (timer) timer.Stop(); });
        Attempt([&] { if (timer) timer.Tick(tick); });
        Attempt([&] { if (surface) surface.LoadCompleted(loaded); });
        Attempt([&] { if (parent) parent.SizeChanged(resized); });
        if (absent) { parent = nullptr; decoration = nullptr; surface = nullptr; timer = nullptr; }
        cleanupRunning = false;
    }

    void Start(Grid const& container, Border const& face, std::uint32_t borderIndex, HMODULE module) {
        parent = container;
        decoration = Canvas();
        decoration.Width(0); decoration.Height(0);
        decoration.HorizontalAlignment(HorizontalAlignment::Left);
        decoration.VerticalAlignment(VerticalAlignment::Top);
        decoration.IsHitTestVisible(false);
        timer = DispatcherTimer();
        timer.Interval(std::chrono::seconds(8));
        tick = timer.Tick([this](auto const&, auto const&) noexcept { Remove(); });
        resized = parent.SizeChanged([this](auto const&, auto const&) noexcept {
            flags.fetch_or(ProbeGeometryChanged); Remove();
        });
        timer.Start();
        flags.fetch_or(ProbeStarted);

        auto resource = FindResourceW(module, MAKEINTRESOURCEW(101), RT_RCDATA);
        if (!resource) throw hresult_error(HRESULT_FROM_WIN32(GetLastError()));
        auto bytes = static_cast<const BYTE*>(LockResource(LoadResource(module, resource)));
        auto size = SizeofResource(module, resource);
        if (!bytes || !size) throw hresult_error(E_FAIL);
        com_ptr<IStream> stream;
        stream.attach(SHCreateMemStream(bytes, size));
        if (!stream) throw hresult_error(E_OUTOFMEMORY);
        Windows::Storage::Streams::IRandomAccessStream random{nullptr};
        check_hresult(CreateRandomAccessStreamOverStream(stream.get(), BSOS_DEFAULT,
            guid_of<Windows::Storage::Streams::IRandomAccessStream>(), put_abi(random)));
        surface = LoadedImageSurface::StartLoadFromStream(random);
        auto compositor = Hosting::ElementCompositionPreview::GetElementVisual(parent).Compositor();
        auto source = compositor.CreateSurfaceBrush(surface);
        source.Stretch(CompositionStretch::Fill);
        auto brush = compositor.CreateNineGridBrush();
        brush.Source(source);
        brush.SetInsets(54.0f);
        brush.SetInsetScales(18.0f / 54.0f);
        brush.IsCenterHollow(false);
        auto visual = compositor.CreateSpriteVisual();
        visual.Brush(brush);
        visual.Size({static_cast<float>(face.ActualWidth()), static_cast<float>(face.ActualHeight())});
        auto origin = face.TransformToVisual(parent).TransformPoint({0, 0});
        visual.Offset({origin.X, origin.Y, 0});
        Hosting::ElementCompositionPreview::SetElementChildVisual(decoration, visual);
        auto expectedContent = parent.Children().GetAt(1);
        auto expectedOuter = VisualTreeHelper::GetParent(parent);
        auto expectedKey = VisualTreeHelper::GetParent(expectedOuter);
        const auto expectedWidth = face.ActualWidth();
        const auto expectedHeight = face.ActualHeight();
        auto dispatcher = parent.Dispatcher();
        loaded = surface.LoadCompleted([this, face, borderIndex, expectedContent, expectedOuter, expectedKey, expectedWidth, expectedHeight, dispatcher](auto const&, LoadedImageSourceLoadCompletedEventArgs const& args) noexcept {
            try {
                const auto status = args.Status();
                dispatcher.RunAsync(Core::CoreDispatcherPriority::Normal,
                    [this, face, borderIndex, expectedContent, expectedOuter, expectedKey, expectedWidth, expectedHeight, status]() noexcept {
                    if (stopping || finished || (flags.load() & ProbeInserted)) return;
                    try {
                if (status != LoadedImageSourceLoadStatus::Success) throw hresult_error(E_FAIL);
                flags.fetch_or(ProbeImageLoaded);
                // The probe owns only this noninteractive decoration, below the native labels.
                auto children = parent.Children();
                if (children.Size() != 2 || children.GetAt(borderIndex) != face ||
                    children.GetAt(1) != expectedContent ||
                    VisualTreeHelper::GetParent(face) != parent ||
                    VisualTreeHelper::GetParent(parent) != expectedOuter ||
                    VisualTreeHelper::GetParent(expectedOuter) != expectedKey ||
                    !face.XamlRoot() || !face.XamlRoot().IsHostVisible() ||
                    face.ActualWidth() != expectedWidth || face.ActualHeight() != expectedHeight)
                    throw hresult_error(E_CHANGED_STATE);
                children.InsertAt(borderIndex + 1, decoration);
                flags.fetch_or(ProbeInserted);
                    } catch (...) { result = to_hresult(); flags.fetch_or(ProbeFailed); Remove(); }
                });
            } catch (...) { result = to_hresult(); flags.fetch_or(ProbeFailed); }
        });
    }
};

// One bounded probe per process. Pinning prevents unloaded timer delegates even if cleanup fails.
FaceProbe& Probe() { static auto value = new FaceProbe; return *value; }
}

bool BeginFaceProbe() noexcept { return !Probe().begun.exchange(true); }

void ObserveFace(IXamlDiagnostics* diagnostics, InstanceHandle handle) noexcept {
    auto& probe = Probe();
    if (probe.selected.load() || !diagnostics) return;
    bool ownsCandidate = false;
    try {
        Windows::Foundation::IInspectable object{nullptr};
        check_hresult(diagnostics->GetIInspectableFromHandle(handle, reinterpret_cast<IInspectable**>(put_abi(object))));
        auto face = object.try_as<Border>();
        if (!face || !face.Dispatcher().HasThreadAccess() || face.ActualWidth() < 36 || face.ActualHeight() < 36) return;
        auto parent = VisualTreeHelper::GetParent(face).try_as<Grid>();
        if (!parent || parent.Children().Size() != 2) return;
        auto outer = VisualTreeHelper::GetParent(parent).try_as<Grid>();
        if (!outer) return;
        auto key = VisualTreeHelper::GetParent(outer);
        if (!key || get_class_name(key) != L"WindowsInternal.ComposableShell.Experiences.TextInputUndocked.Controls.KeyboardKey") return;
        if (!face.XamlRoot() || !face.XamlRoot().IsHostVisible()) return;
        std::uint32_t index = 0;
        if (!parent.Children().IndexOf(face, index) || index != 0 || !parent.Children().GetAt(1).try_as<ContentControl>()) return;
        if (probe.selected.exchange(true)) return;
        ownsCandidate = true;
        HMODULE module = nullptr;
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&KeyboardTapId), &module)) throw hresult_error(HRESULT_FROM_WIN32(GetLastError()));
        probe.Start(parent, face, index, module);
    } catch (...) {
        if (ownsCandidate) { probe.result = to_hresult(); probe.flags.fetch_or(ProbeFailed); probe.Remove(); }
    }
}
void ReadFaceProbe(Report& report) noexcept {
    report.probeFlags = Probe().flags.load();
    report.probeResult = Probe().result.load();
}
}
