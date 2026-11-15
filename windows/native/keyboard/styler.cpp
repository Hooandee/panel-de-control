#include "styler.h"
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
#include <winrt/Windows.UI.Xaml.Data.h>
#include <winrt/Windows.UI.Xaml.Input.h>
#include <winrt/Windows.UI.Xaml.Hosting.h>
#include <winrt/Windows.UI.Xaml.Media.h>
#include "terciopelo.h"
#include <array>
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <set>
#include <vector>

namespace keyboard {
namespace {
using namespace winrt;
using namespace Windows::UI;
using namespace Windows::UI::Xaml;
using namespace Windows::UI::Xaml::Controls;
using namespace Windows::UI::Xaml::Media;
using namespace Windows::UI::Composition;
using Windows::Foundation::IInspectable;
constexpr wchar_t KeyType[] = L"WindowsInternal.ComposableShell.Experiences.TextInputUndocked.Controls.KeyboardKey";
constexpr wchar_t GridType[] = L"WindowsInternal.ComposableShell.Experiences.TextInputUndocked.Controls.KeyboardGrid";
std::atomic<bool> requested{false};
std::atomic<ULONGLONG> lease{0}, generation{0};
std::atomic<DWORD> owner{0};
std::mutex receiptGate;
Report receipt;

void Fail(HRESULT error) noexcept {
    std::lock_guard lock(receiptGate);
    receipt.styleResult = error;
    receipt.phase = StylePhase::Failed;
}
void Catalog(FrameworkElement const& element) {
    for (auto const& group : VisualStateManager::GetVisualStateGroups(element)) {
        for (auto const& state : group.States()) {
            auto text = to_string(group.Name()) + "." + to_string(state.Name());
            if (text.empty() || text.size() >= TypeLength) continue;
            bool safe = true;
            for (char c : text) if (!TypeCharacter(c)) safe = false;
            if (!safe) continue;
            std::lock_guard lock(receiptGate);
            bool found = false;
            for (unsigned i = 0; i < receipt.stateCount; ++i)
                if (text == receipt.states[i]) found = true;
            if (!found && receipt.stateCount < MaxStates)
                strcpy_s(receipt.states[receipt.stateCount++], text.c_str());
        }
    }
}
struct Property {
    FrameworkElement element{nullptr};
    DependencyProperty property{nullptr};
    IInspectable original{nullptr};
    Data::Binding binding{nullptr};
    bool restored = false;
    Property(FrameworkElement const& value, DependencyProperty const& dp) : element(value), property(dp) {
        original = element.ReadLocalValue(dp);
        if (auto expression = element.GetBindingExpression(dp)) binding = expression.ParentBinding();
    }
    void Restore() {
        if (restored) return;
        if (binding) { element.ClearValue(property); element.SetBinding(property, binding); }
        else if (original == DependencyProperty::UnsetValue()) element.ClearValue(property);
        else element.SetValue(property, original);
        restored = true;
    }
};
struct Label {
    TextBlock element{nullptr};
    std::unique_ptr<Property> foreground;
    bool icon = false;
};
struct Cell {
    Border face{nullptr};
    Grid parent{nullptr};
    FrameworkElement key{nullptr};
    Grid outer{nullptr};
    Canvas canvas{nullptr};
    SpriteVisual visual{nullptr};
    CompositionNineGridBrush brush{nullptr};
    std::vector<Label> labels;
    bool retiring = false;
    bool inserted = false, unloaded = false, hover = false, pressed = false, focused = false;
    std::vector<std::pair<RoutedEvent, IInspectable>> handlers;
    event_token size{}, removed{}, gotFocus{}, lostFocus{};
    std::vector<std::pair<VisualStateGroup, event_token>> groups;
    std::array<CompositionSurfaceBrush, 5> sources{nullptr, nullptr, nullptr, nullptr, nullptr};

    void Paint() {
        if (retiring || !inserted) return;
        const unsigned index = pressed ? (focused ? 4 : 3) : focused ? 2 : hover ? 1 : 0;
        brush.Source(sources[index]);
        for (auto& label : labels)
            label.element.Foreground(SolidColorBrush(pressed ? terciopelo::Pressed : label.icon ? terciopelo::Accent : terciopelo::Ink));
    }
    void Geometry() {
        if (retiring || !visual || !parent || face.ActualWidth() <= 0 || face.ActualHeight() <= 0) return;
        const auto origin = face.TransformToVisual(parent).TransformPoint({0, 0});
        visual.Offset({origin.X - terciopelo::Outset, origin.Y - terciopelo::Outset, 0});
        visual.Size({static_cast<float>(face.ActualWidth()) + 2 * terciopelo::Outset,
                     static_cast<float>(face.ActualHeight()) + 2 * terciopelo::Outset});
    }
    void ReadLabels(DependencyObject const& root, unsigned depth = 0) {
        if (depth > 6 || labels.size() >= 12) return;
        if (auto text = root.try_as<TextBlock>()) {
            auto family = text.FontFamily().Source();
            const bool icon = std::wstring_view(family).find(L"Icon") != std::wstring_view::npos ||
                std::wstring_view(family).find(L"Symbol") != std::wstring_view::npos ||
                std::wstring_view(family).find(L"MDL2") != std::wstring_view::npos;
            labels.push_back({text, std::make_unique<Property>(text, TextBlock::ForegroundProperty()), icon});
        }
        for (int i = 0, n = VisualTreeHelper::GetChildrenCount(root); i < n; ++i)
            ReadLabels(VisualTreeHelper::GetChild(root, i), depth + 1);
    }
    void Pointer(RoutedEvent const& event, int action) {
        Windows::UI::Xaml::Input::PointerEventHandler handler([this, action](IInspectable const&, Windows::UI::Xaml::Input::PointerRoutedEventArgs const&) noexcept {
            try {
                if (action == 0) pressed = true;
                else if (action == 1) pressed = false;
                else if (action == 2) hover = true;
                else if (action == 3) { hover = false; pressed = false; }
                Paint();
            } catch (...) { Fail(to_hresult()); requested = false; }
        });
        auto boxed = box_value(handler);
        key.AddHandler(event, boxed, true);
        handlers.emplace_back(event, boxed);
    }
    void Insert(std::array<LoadedImageSurface, 6> const& surfaces) {
        auto children = parent.Children();
        if (children.Size() != 2 || children.GetAt(0) != face || !children.GetAt(1).try_as<ContentControl>()) {
            unloaded = true; return;
        }
        canvas = Canvas(); canvas.Width(0); canvas.Height(0);
        canvas.HorizontalAlignment(HorizontalAlignment::Left); canvas.VerticalAlignment(VerticalAlignment::Top);
        canvas.IsHitTestVisible(false);
        auto compositor = Hosting::ElementCompositionPreview::GetElementVisual(parent).Compositor();
        for (unsigned i = 0; i < sources.size(); ++i) {
            sources[i] = compositor.CreateSurfaceBrush(surfaces[i]); sources[i].Stretch(CompositionStretch::Fill);
        }
        brush = compositor.CreateNineGridBrush();
        brush.SetInsets(terciopelo::Slice); brush.SetInsetScales(terciopelo::Border / terciopelo::Slice);
        brush.IsCenterHollow(false); brush.Source(sources[0]);
        visual = compositor.CreateSpriteVisual(); visual.Brush(brush); Geometry();
        Hosting::ElementCompositionPreview::SetElementChildVisual(canvas, visual);
        ReadLabels(children.GetAt(1));
        children.InsertAt(1, canvas); inserted = true;
        size = face.SizeChanged([this](auto const&, auto const&) noexcept { try { Geometry(); } catch (...) { unloaded = true; } });
        removed = key.Unloaded([this](auto const&, auto const&) noexcept { unloaded = true; });
        Pointer(UIElement::PointerPressedEvent(), 0); Pointer(UIElement::PointerReleasedEvent(), 1);
        Pointer(UIElement::PointerEnteredEvent(), 2); Pointer(UIElement::PointerExitedEvent(), 3);
        Pointer(UIElement::PointerCanceledEvent(), 3); Pointer(UIElement::PointerCaptureLostEvent(), 3);
        RoutedEventHandler got([this](auto const&, auto const&) noexcept { try { focused = true; Paint(); } catch (...) { Fail(to_hresult()); requested = false; } });
        RoutedEventHandler lost([this](auto const&, auto const&) noexcept { try { focused = false; Paint(); } catch (...) { Fail(to_hresult()); requested = false; } });
        gotFocus = key.GotFocus(got);
        lostFocus = key.LostFocus(lost);
        Catalog(key); Catalog(parent);
        if (auto outer = VisualTreeHelper::GetParent(parent).try_as<FrameworkElement>()) Catalog(outer);
        Paint();
    }
    bool Restore() noexcept {
        retiring = true;
        bool clean = true;
        auto attempt = [&](auto action) { try { action(); } catch (...) { clean = false; Fail(to_hresult()); } };
        attempt([&] {
            if (canvas) {
                unsigned index = 0;
                if (parent.Children().IndexOf(canvas, index)) parent.Children().RemoveAt(index);
                if (parent.Children().IndexOf(canvas, index)) throw hresult_error(E_FAIL);
                Hosting::ElementCompositionPreview::SetElementChildVisual(canvas, nullptr);
            }
        });
        for (auto& label : labels) attempt([&] { label.foreground->Restore(); });
        for (auto& pair : handlers) attempt([&] { key.RemoveHandler(pair.first, pair.second); });
        attempt([&] { if (size.value) face.SizeChanged(size); });
        attempt([&] { if (removed.value) key.Unloaded(removed); });
        attempt([&] { if (gotFocus.value) key.GotFocus(gotFocus); });
        attempt([&] { if (lostFocus.value) key.LostFocus(lostFocus); });
        if (clean) { handlers.clear(); labels.clear(); inserted = false; }
        return clean;
    }
};
struct Plate {
    Grid parent{nullptr}; Canvas canvas{nullptr}; SpriteVisual visual{nullptr}; event_token size{};
    void Geometry() { visual.Size({static_cast<float>(parent.ActualWidth()), static_cast<float>(parent.ActualHeight())}); }
    void Insert(Grid const& value, LoadedImageSurface const& surface) {
        parent = value; canvas = Canvas(); canvas.Width(0); canvas.Height(0);
        canvas.HorizontalAlignment(HorizontalAlignment::Left); canvas.VerticalAlignment(VerticalAlignment::Top); canvas.IsHitTestVisible(false);
        auto compositor = Hosting::ElementCompositionPreview::GetElementVisual(parent).Compositor();
        visual = compositor.CreateSpriteVisual();
        auto brush = compositor.CreateSurfaceBrush(surface); brush.Stretch(CompositionStretch::Fill);
        visual.Brush(brush); Geometry();
        Hosting::ElementCompositionPreview::SetElementChildVisual(canvas, visual);
        parent.Children().InsertAt(0, canvas);
        size = parent.SizeChanged([this](auto const&, auto const&) noexcept { try { Geometry(); } catch (...) { Fail(to_hresult()); requested = false; } });
    }
    bool Restore() noexcept {
        try {
            unsigned index = 0;
            if (canvas && parent.Children().IndexOf(canvas, index)) parent.Children().RemoveAt(index);
            if (canvas && parent.Children().IndexOf(canvas, index)) throw hresult_error(E_FAIL);
            if (size.value) parent.SizeChanged(size);
            if (canvas) Hosting::ElementCompositionPreview::SetElementChildVisual(canvas, nullptr);
            return true;
        } catch (...) { Fail(to_hresult()); return false; }
    }
};
struct Engine {
    ULONGLONG epoch = 0;
    DispatcherTimer timer{nullptr}; event_token tick{};
    std::array<LoadedImageSurface, 6> surfaces{nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};
    std::array<event_token, 6> completions{};
    std::array<bool, 6> ready{};
    std::vector<std::unique_ptr<Cell>> cells;
    std::vector<weak_ref<FrameworkElement>> candidates;
    std::vector<std::unique_ptr<Plate>> plates;
    unsigned restored = 0, cleanupAttempts = 0;
    bool started = false;

    void Start(FrameworkElement const& anchor, ULONGLONG value) {
        if (started) return;
        epoch = value; ready.fill(false); restored = 0; cleanupAttempts = 0;
        HMODULE module = nullptr;
        check_bool(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&KeyboardStyleId), &module));
        timer = DispatcherTimer(); timer.Interval(std::chrono::milliseconds(250));
        tick = timer.Tick([this](auto const&, auto const&) noexcept { Update(); }); timer.Start(); started = true;
        auto dispatcher = anchor.Dispatcher();
        for (unsigned i = 0; i < surfaces.size(); ++i) {
            auto resource = FindResourceW(module, MAKEINTRESOURCEW(101 + i), RT_RCDATA);
            if (!resource) throw hresult_error(HRESULT_FROM_WIN32(GetLastError()));
            auto bytes = static_cast<const BYTE*>(LockResource(LoadResource(module, resource)));
            auto count = SizeofResource(module, resource);
            com_ptr<IStream> stream; stream.attach(SHCreateMemStream(bytes, count));
            if (!stream) throw hresult_error(E_OUTOFMEMORY);
            Windows::Storage::Streams::IRandomAccessStream random{nullptr};
            check_hresult(CreateRandomAccessStreamOverStream(stream.get(), BSOS_DEFAULT,
                guid_of<Windows::Storage::Streams::IRandomAccessStream>(), put_abi(random)));
            surfaces[i] = LoadedImageSurface::StartLoadFromStream(random);
            completions[i] = surfaces[i].LoadCompleted([this, dispatcher, value, i](auto const&, LoadedImageSourceLoadCompletedEventArgs const& args) noexcept {
                try {
                    auto status = args.Status();
                    dispatcher.RunAsync(Core::CoreDispatcherPriority::Normal, [this, value, i, status]() noexcept {
                        if (!requested || epoch != value || generation != value) return;
                        if (status == LoadedImageSourceLoadStatus::Success) ready[i] = true;
                        else { Fail(E_FAIL); requested = false; }
                    });
                } catch (...) { Fail(to_hresult()); requested = false; }
            });
        }
    }
    void Add(Border const& face, ULONGLONG value) {
        if (!requested || generation != value) return;
        for (auto const& cell : cells) if (cell->face == face) return;
        auto parent = VisualTreeHelper::GetParent(face).try_as<Grid>();
        if (!parent || parent.Children().Size() != 2 || parent.Children().GetAt(0) != face ||
            !parent.Children().GetAt(1).try_as<ContentControl>()) return;
        auto outer = VisualTreeHelper::GetParent(parent).try_as<Grid>();
        if (!outer) return;
        auto key = VisualTreeHelper::GetParent(outer).try_as<FrameworkElement>();
        if (!key || get_class_name(key) != KeyType) return;
        if (cells.size() >= 256) { Fail(E_BOUNDS); requested = false; return; }
        auto cell = std::make_unique<Cell>(); cell->face = face; cell->parent = parent; cell->key = key; cell->outer = outer;
        cells.push_back(std::move(cell));
    }
    void AddCandidate(FrameworkElement const& key, ULONGLONG value) {
        if (!requested || generation != value || get_class_name(key) != KeyType) return;
        DWORD empty = 0, thread = GetCurrentThreadId();
        if (!owner.compare_exchange_strong(empty, thread) && empty != thread) return;
        Start(key, value);
        for (auto const& weak : candidates) if (weak.get() == key) return;
        if (candidates.size() >= 256) { Fail(E_BOUNDS); requested = false; return; }
        candidates.push_back(make_weak(key));
    }
    void FindFace(FrameworkElement const& key) {
        if (VisualTreeHelper::GetChildrenCount(key) != 1) return;
        auto outer = VisualTreeHelper::GetChild(key, 0).try_as<Grid>();
        if (!outer || outer.Children().Size() != 1) return;
        auto parent = outer.Children().GetAt(0).try_as<Grid>();
        if (!parent || parent.Children().Size() < 2) return;
        if (auto face = parent.Children().GetAt(0).try_as<Border>()) Add(face, epoch);
    }
    void EnsurePlate(Cell const& cell) {
        auto parent = VisualTreeHelper::GetParent(cell.key).try_as<Grid>();
        if (!parent) return;
        for (auto const& plate : plates) if (plate->parent == parent) return;
        auto grid = VisualTreeHelper::GetParent(parent);
        if (!grid || get_class_name(grid) != GridType) return;
        for (auto const& child : parent.Children()) if (get_class_name(child) != KeyType) return;
        auto plate = std::make_unique<Plate>();
        auto pointer = plate.get(); plates.push_back(std::move(plate)); pointer->Insert(parent, surfaces[5]);
    }
    void Update() noexcept {
        try {
            if (GetTickCount64() >= lease.load()) requested = false;
            bool stopping = !requested || epoch != generation;
            bool loaded = true; for (bool value : ready) loaded &= value;
            unsigned visible = 0, styled = 0, pending = 0;
            if (!stopping) for (auto it = candidates.begin(); it != candidates.end();) {
                auto key = it->get();
                if (!key || !VisualTreeHelper::GetParent(key)) { it = candidates.erase(it); continue; }
                if (key.XamlRoot() && key.XamlRoot().IsHostVisible() && key.ActualWidth() > 0 && key.ActualHeight() > 0) {
                    ++visible; FindFace(key);
                }
                ++it;
            }
            for (auto it = cells.begin(); it != cells.end();) {
                auto& cell = **it;
                if (stopping || cell.unloaded || !VisualTreeHelper::GetParent(cell.key) ||
                    VisualTreeHelper::GetParent(cell.face) != cell.parent ||
                    VisualTreeHelper::GetParent(cell.parent) != cell.outer ||
                    VisualTreeHelper::GetParent(cell.outer) != cell.key) {
                    const bool wasInserted = cell.inserted;
                    if (cell.Restore()) { if (wasInserted) ++restored; it = cells.erase(it); continue; }
                } else if (cell.face.XamlRoot() && cell.face.XamlRoot().IsHostVisible() &&
                           cell.face.ActualWidth() > 0 && cell.face.ActualHeight() > 0) {
                    if (!cell.inserted && loaded) { EnsurePlate(cell); cell.Insert(surfaces); }
                    unsigned childIndex = 0;
                    if (cell.inserted && cell.parent.Children().IndexOf(cell.canvas, childIndex) && childIndex == 1 &&
                        Hosting::ElementCompositionPreview::GetElementChildVisual(cell.canvas) == cell.visual) ++styled;
                    else if (cell.inserted) cell.unloaded = true;
                }
                ++it;
            }
            for (auto it = plates.begin(); it != plates.end();) {
                if (stopping || !VisualTreeHelper::GetParent((*it)->parent)) {
                    if ((*it)->Restore()) { it = plates.erase(it); continue; }
                }
                ++it;
            }
            pending = visible > styled ? visible - styled : 0;
            const bool clean = stopping && cells.empty() && plates.empty();
            if (stopping && !clean && ++cleanupAttempts > 12) {
                Fail(E_FAIL); timer.Stop(); return;
            }
            {
                std::lock_guard lock(receiptGate);
                receipt.keyCount = stopping ? static_cast<unsigned>(cells.size()) : visible;
                receipt.styledKeys = stopping ? 0 : styled;
                receipt.pendingKeys = pending; receipt.restoredKeys = restored;
                if (clean && SUCCEEDED(receipt.styleResult)) receipt.phase = StylePhase::Idle;
                else if (FAILED(receipt.styleResult)) receipt.phase = StylePhase::Failed;
                else if (stopping) receipt.phase = StylePhase::Restoring;
                else if (!visible) receipt.phase = StylePhase::Waiting;
                else receipt.phase = loaded && styled == visible && !pending ? StylePhase::Applied : StylePhase::Applying;
            }
            if (clean) {
                timer.Stop(); timer.Tick(tick); timer = nullptr;
                for (unsigned i = 0; i < surfaces.size(); ++i) {
                    if (surfaces[i]) surfaces[i].LoadCompleted(completions[i]); surfaces[i] = nullptr;
                }
                candidates.clear(); started = false; owner = 0;
            }
        } catch (...) { Fail(to_hresult()); requested = false; }
    }
};
Engine& Current() { static auto engine = new Engine; return *engine; }
}

bool BeginStyleSession() noexcept {
    if (requested.exchange(true)) return false;
    if (owner.load()) { requested = false; return false; }
    ++generation; lease = GetTickCount64() + 4000;
    std::lock_guard lock(receiptGate); receipt = {}; receipt.phase = StylePhase::Waiting;
    return true;
}
void RenewStyleLease() noexcept { if (requested) lease = GetTickCount64() + 4000; }
void StopStyleSession() noexcept {
    requested = false;
    if (!owner.load()) { std::lock_guard lock(receiptGate); receipt.phase = StylePhase::Idle; }
}
void ObserveStyle(IXamlDiagnostics* diagnostics, InstanceHandle handle) noexcept {
    if (!requested || !diagnostics) return;
    try {
        IInspectable object{nullptr};
        check_hresult(diagnostics->GetIInspectableFromHandle(handle, reinterpret_cast<::IInspectable**>(put_abi(object))));
        auto key = object.try_as<FrameworkElement>();
        if (!key || !key.Dispatcher().HasThreadAccess() || get_class_name(key) != KeyType) return;
        const auto thread = owner.load();
        if (thread && thread != GetCurrentThreadId()) return;
        const auto value = generation.load();
        key.Dispatcher().RunAsync(Core::CoreDispatcherPriority::Normal, [key, value]() noexcept {
            try { Current().AddCandidate(key, value); }
            catch (...) {
                Fail(to_hresult()); requested = false;
                if (Current().started) Current().Update(); else owner = 0;
            }
        });
    } catch (...) { Fail(to_hresult()); requested = false; }
}

void ReadStyleSession(Report& report) noexcept {
    std::lock_guard lock(receiptGate);
    report.phase = receipt.phase; report.keyCount = receipt.keyCount; report.styledKeys = receipt.styledKeys;
    report.restoredKeys = receipt.restoredKeys; report.pendingKeys = receipt.pendingKeys;
    report.styleResult = receipt.styleResult; report.stateCount = receipt.stateCount;
    memcpy(report.states, receipt.states, sizeof(receipt.states));
}
}
