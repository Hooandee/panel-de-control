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
#include "font_resource.h"
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
constexpr wchar_t SuggestionsType[] = L"WindowsInternal.ComposableShell.Experiences.SuggestionUIUndocked.SuggestionUIContainer";
constexpr wchar_t BarType[] = L"WindowsInternal.ComposableShell.Experiences.TextInputUndocked.Controls.GripperBar";
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
    IInspectable owned{nullptr};
    bool assigned = false, restoring = false, restored = false;
    Property(FrameworkElement const& value, DependencyProperty const& dp) : element(value), property(dp) { Capture(); }
    void Capture() {
        original = element.ReadLocalValue(property);
        binding = nullptr;
        if (auto expression = element.GetBindingExpression(property)) binding = expression.ParentBinding();
    }
    void Assign(IInspectable const& value) {
        if (element.GetValue(property) == value) return;
        if (assigned && element.ReadLocalValue(property) != owned) Capture();
        element.SetValue(property, value); owned = value; assigned = true; restoring = false; restored = false;
    }
    void Restore() {
        if (restored || !assigned) return;
        if (!restoring && element.ReadLocalValue(property) != owned) { restored = true; return; }
        restoring = true;
        if (binding) { element.ClearValue(property); element.SetBinding(property, binding); }
        else if (original == DependencyProperty::UnsetValue()) element.ClearValue(property);
        else element.SetValue(property, original);
        if (binding) {
            auto expression = element.GetBindingExpression(property);
            if (!expression || expression.ParentBinding() != binding) throw hresult_error(E_FAIL);
        } else if (element.ReadLocalValue(property) != original) throw hresult_error(E_FAIL);
        restored = true;
    }

};
struct Label {
    TextBlock element{nullptr};
    std::unique_ptr<Property> foreground;
    std::unique_ptr<Property> font;
    bool icon = false, secondary = false;
};
bool IdentityTransform(Transform const& value) {
    if (!value) return true;
    auto origin = value.TransformPoint({0, 0});
    auto horizontal = value.TransformPoint({1, 0});
    auto vertical = value.TransformPoint({0, 1});
    return origin.X == 0 && origin.Y == 0 && horizontal.X == 1 && horizontal.Y == 0 && vertical.X == 0 && vertical.Y == 1;
}
struct Cell {
    Border face{nullptr};
    Grid parent{nullptr};
    FrameworkElement key{nullptr};
    Grid outer{nullptr};
    ContentControl content{nullptr};
    std::unique_ptr<Property> contentTransform;
    TranslateTransform pressedTransform;
    FontFamily font{nullptr};
    SolidColorBrush ink{terciopelo::Ink}, soft{terciopelo::SoftInk}, accent{terciopelo::Accent}, pressedInk{terciopelo::Pressed};
    Canvas canvas{nullptr};
    SpriteVisual visual{nullptr};
    CompositionNineGridBrush brush{nullptr};
    Canvas dustCanvas{nullptr};
    ContainerVisual dust{nullptr};
    SpriteVisual dustStrip{nullptr};
    Vector3KeyFrameAnimation dustFrames{nullptr};
    ScalarKeyFrameAnimation dustFade{nullptr};
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
        if (contentTransform) {
            if (pressed && content.RenderTransform() != pressedTransform && !IdentityTransform(content.RenderTransform())) {
                contentTransform->Restore(); contentTransform.reset();
            } else if (pressed) contentTransform->Assign(pressedTransform);
            else contentTransform->Restore();
        }
        for (auto& label : labels) {
            label.foreground->Assign(label.secondary ? soft : pressed ? pressedInk : label.icon ? accent : ink);
            if (label.font) label.font->Assign(font);
        }
    }
    void Strike() {
        if (retiring || !dust) return;
        dustStrip.StartAnimation(L"Offset", dustFrames);
        dust.StartAnimation(L"Opacity", dustFade);
    }
    void Geometry() {
        if (retiring || !visual || !parent || face.ActualWidth() <= 0 || face.ActualHeight() <= 0) return;
        const auto origin = face.TransformToVisual(parent).TransformPoint({0, 0});
        visual.Offset({origin.X - terciopelo::Outset, origin.Y - terciopelo::Outset, 0});
        visual.Size({static_cast<float>(face.ActualWidth()) + 2 * terciopelo::Outset,
                     static_cast<float>(face.ActualHeight()) + 2 * terciopelo::Outset});
        if (dust) dust.Offset({origin.X + static_cast<float>(face.ActualWidth()) / 2 - 63,
            origin.Y + static_cast<float>(face.ActualHeight()) / 2 - 66, 0});
    }
    void FindLabels(DependencyObject const& root, std::vector<TextBlock>& found, unsigned depth = 0) {
        if (depth > 6 || found.size() >= 12) return;
        if (auto text = root.try_as<TextBlock>()) found.push_back(text);
        for (int i = 0, n = VisualTreeHelper::GetChildrenCount(root); i < n; ++i)
            FindLabels(VisualTreeHelper::GetChild(root, i), found, depth + 1);
    }
    bool ReconcileLabels() {
        auto children = parent.Children();
        if (children.Size() != 4 || children.GetAt(0) != face || children.GetAt(1) != canvas || children.GetAt(3) != dustCanvas ||
            Hosting::ElementCompositionPreview::GetElementChildVisual(dustCanvas) != dust) return false;
        auto current = children.GetAt(2).try_as<ContentControl>();
        if (!current) return false;
        if (current != content) {
            if (contentTransform) contentTransform->Restore();
            contentTransform.reset(); content = current;
        }
        if (!contentTransform) {
            if (IdentityTransform(content.RenderTransform())) {
                contentTransform = std::make_unique<Property>(content, UIElement::RenderTransformProperty()); pressedTransform.Y(3);
            }
        }
        std::vector<TextBlock> found;
        FindLabels(content, found);
        for (auto it = labels.begin(); it != labels.end();) {
            bool present = false;
            for (auto const& text : found) if (text == it->element) present = true;
            if (!present) {
                it->foreground->Restore(); if (it->font) it->font->Restore();
                it = labels.erase(it);
            } else ++it;
        }
        for (auto const& text : found) {
            bool known = false;
            auto family = text.FontFamily().Source();
            const bool icon = std::wstring_view(family).find(L"Icon") != std::wstring_view::npos ||
                std::wstring_view(family).find(L"Symbol") != std::wstring_view::npos ||
                std::wstring_view(family).find(L"MDL2") != std::wstring_view::npos;
            for (auto& label : labels) if (label.element == text) {
                known = true;
                if (label.icon != icon) {
                    if (icon && label.font) { label.font->Restore(); label.font.reset(); }
                    else if (!icon) label.font = std::make_unique<Property>(text, TextBlock::FontFamilyProperty());
                    label.icon = icon;
                }
            }
            if (known) continue;
            labels.push_back({text, std::make_unique<Property>(text, TextBlock::ForegroundProperty()),
                icon ? nullptr : std::make_unique<Property>(text, TextBlock::FontFamilyProperty()), icon, false});
        }
        double primarySize = 0;
        for (auto const& label : labels) if (!label.icon) primarySize = std::max(primarySize, label.element.FontSize());
        for (auto& label : labels) label.secondary = !label.icon && label.element.FontSize() + 1 < primarySize;
        Paint();
        for (auto const& label : labels) {
            Brush expected = label.secondary ? soft : pressed ? pressedInk : label.icon ? accent : ink;
            if (label.element.Foreground() != expected || (label.font && label.element.FontFamily() != font)) return false;
        }
        return true;
    }
    void Pointer(RoutedEvent const& event, int action) {
        Windows::UI::Xaml::Input::PointerEventHandler handler([this, action](IInspectable const&, Windows::UI::Xaml::Input::PointerRoutedEventArgs const&) noexcept {
            try {
                if (retiring) return;
                if (action == 0) { pressed = true; Strike(); }
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
    void Insert(std::array<LoadedImageSurface, 7> const& surfaces, FontFamily const& desiredFont) {
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
        visual = compositor.CreateSpriteVisual(); visual.Brush(brush);
        dustCanvas = Canvas(); dustCanvas.Width(0); dustCanvas.Height(0);
        dustCanvas.HorizontalAlignment(HorizontalAlignment::Left); dustCanvas.VerticalAlignment(VerticalAlignment::Top); dustCanvas.IsHitTestVisible(false);
        dust = compositor.CreateContainerVisual(); dust.Size({126, 98}); dust.Opacity(0); dust.Clip(compositor.CreateInsetClip());
        dustStrip = compositor.CreateSpriteVisual(); dustStrip.Size({2268, 98});
        auto dustBrush = compositor.CreateSurfaceBrush(surfaces[6]); dustBrush.Stretch(CompositionStretch::Fill);
        dustStrip.Brush(dustBrush); dust.Children().InsertAtTop(dustStrip);
        Hosting::ElementCompositionPreview::SetElementChildVisual(dustCanvas, dust);
        auto steps = compositor.CreateStepEasingFunction(17);
        steps.IsInitialStepSingleFrame(false); steps.IsFinalStepSingleFrame(true);
        dustFrames = compositor.CreateVector3KeyFrameAnimation();
        dustFrames.InsertKeyFrame(0, {0, 0, 0}); dustFrames.InsertKeyFrame(1, {-2142, 0, 0}, steps);
        dustFrames.Duration(std::chrono::milliseconds(720));
        dustFade = compositor.CreateScalarKeyFrameAnimation();
        auto linear = compositor.CreateLinearEasingFunction();
        dustFade.InsertKeyFrame(0, 1); dustFade.InsertKeyFrame(0.8f, 1, linear); dustFade.InsertKeyFrame(1, 0, linear);
        dustFade.Duration(std::chrono::milliseconds(720)); Geometry();
        Hosting::ElementCompositionPreview::SetElementChildVisual(canvas, visual);
        content = children.GetAt(1).as<ContentControl>(); font = desiredFont;
        children.InsertAt(1, canvas); inserted = true; children.Append(dustCanvas);
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
        ReconcileLabels();
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
        attempt([&] {
            if (dustCanvas) {
                unsigned index = 0;
                if (parent.Children().IndexOf(dustCanvas, index)) parent.Children().RemoveAt(index);
                if (parent.Children().IndexOf(dustCanvas, index)) throw hresult_error(E_FAIL);
                Hosting::ElementCompositionPreview::SetElementChildVisual(dustCanvas, nullptr);
            }
        });
        if (contentTransform) attempt([&] { contentTransform->Restore(); });
        for (auto& label : labels) {
            attempt([&] { label.foreground->Restore(); });
            if (label.font) attempt([&] { label.font->Restore(); });
        }
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
struct Chrome {
    Grid root{nullptr};
    FrameworkElement bar{nullptr};
    Plate plate;
    bool confirmed = false;
    SolidColorBrush background{terciopelo::Background}, clear{Color{0, 0, 0, 0}}, accent{terciopelo::Accent};
    struct Entry { std::unique_ptr<Property> property; IInspectable value; };
    std::vector<Entry> properties;
    void Set(FrameworkElement const& element, DependencyProperty const& dp, IInspectable const& value) {
        for (auto& entry : properties) if (entry.property->element == element && entry.property->property == dp) {
            entry.property->Assign(value); return;
        }
        if (properties.size() >= 256) throw hresult_error(E_BOUNDS);
        auto property = std::make_unique<Property>(element, dp);
        properties.push_back({std::move(property), value});
        properties.back().property->Assign(value);
    }
    void StyleBar(DependencyObject const& node, unsigned depth = 0) {
        if (depth > 10) throw hresult_error(E_BOUNDS);
        if (node.try_as<WebView>() || node.try_as<TextBox>() || node.try_as<PasswordBox>()) return;
        if (auto panel = node.try_as<Panel>()) Set(panel, Panel::BackgroundProperty(), clear);
        if (auto border = node.try_as<Border>()) Set(border, Border::BackgroundProperty(), clear);
        if (auto control = node.try_as<Control>()) {
            Set(control, Control::BackgroundProperty(), clear);
            Set(control, Control::ForegroundProperty(), accent);
        }
        if (auto text = node.try_as<TextBlock>()) Set(text, TextBlock::ForegroundProperty(), accent);
        if (auto icon = node.try_as<IconElement>()) Set(icon, IconElement::ForegroundProperty(), accent);
        for (int i = 0, n = VisualTreeHelper::GetChildrenCount(node); i < n; ++i)
            StyleBar(VisualTreeHelper::GetChild(node, i), depth + 1);
    }
    bool Update() {
        if (VisualTreeHelper::GetParent(bar) != root) return false;
        unsigned index = 0;
        if (!root.Children().IndexOf(plate.canvas, index) || index != 0 ||
            Hosting::ElementCompositionPreview::GetElementChildVisual(plate.canvas) != plate.visual) return false;
        for (auto it = properties.begin(); it != properties.end();) {
            DependencyObject node = it->property->element;
            for (unsigned depth = 0; node && node != root && depth < 16; ++depth) node = VisualTreeHelper::GetParent(node);
            if (node != root) { it->property->Restore(); it = properties.erase(it); }
            else ++it;
        }
        Set(root, Panel::BackgroundProperty(), background);
        for (auto const& child : root.Children()) {
            auto type = get_class_name(child);
            if (child == bar || type == SuggestionsType || type == L"Windows.UI.Xaml.Controls.Grid" || type == L"Windows.UI.Xaml.Controls.Border") StyleBar(child);
        }
        for (auto const& entry : properties)
            if (entry.property->element.GetValue(entry.property->property) != entry.value) return false;
        return true;
    }
    bool Restore() noexcept {
        bool clean = plate.Restore();
        for (auto& entry : properties) {
            try { entry.property->Restore(); }
            catch (...) { clean = false; Fail(to_hresult()); }
        }
        return clean;
    }
};
struct Engine {
    ULONGLONG epoch = 0, loadingStarted = 0;
    FontResource font;
    bool fontReady = false;
    unsigned fontChecks = 0;
    DispatcherTimer timer{nullptr}; event_token tick{};
    std::array<LoadedImageSurface, 7> surfaces{nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};
    std::array<event_token, 7> completions{};
    std::array<bool, 7> ready{};
    std::vector<std::unique_ptr<Cell>> cells;
    std::vector<weak_ref<FrameworkElement>> candidates;
    std::vector<std::unique_ptr<Plate>> plates;
    std::vector<std::unique_ptr<Chrome>> chromes;
    unsigned restored = 0, cleanupAttempts = 0;
    bool started = false;

    void Start(FrameworkElement const& anchor, ULONGLONG value) {
        if (started) return;
        epoch = value; loadingStarted = GetTickCount64(); ready.fill(false); restored = 0; cleanupAttempts = 0; fontReady = false; fontChecks = 0;
        HMODULE module = nullptr;
        check_bool(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&KeyboardStyleId), &module));
        timer = DispatcherTimer(); timer.Interval(std::chrono::milliseconds(250));
        tick = timer.Tick([this](auto const&, auto const&) noexcept { Update(); }); timer.Start(); started = true;
        font.Load(module);
        auto dispatcher = anchor.Dispatcher();
        for (unsigned i = 0; i < surfaces.size(); ++i) {
            auto resource = FindResourceW(module, MAKEINTRESOURCEW(i == 6 ? 108 : 101 + i), RT_RCDATA);
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
    bool EnsureChrome(Cell const& cell) {
        auto keys = VisualTreeHelper::GetParent(cell.key);
        if (!keys) return false;
        auto grid = VisualTreeHelper::GetParent(keys);
        if (!grid || get_class_name(grid) != GridType) return false;
        auto root = VisualTreeHelper::GetParent(grid).try_as<Grid>();
        if (!root) return false;
        for (auto const& chrome : chromes) if (chrome->root == root) return chrome->confirmed;
        FrameworkElement bar{nullptr};
        for (auto const& child : root.Children()) if (get_class_name(child) == BarType) bar = child.as<FrameworkElement>();
        if (!bar || chromes.size() >= 8) return false;
        auto chrome = std::make_unique<Chrome>(); chrome->root = root; chrome->bar = bar;
        auto pointer = chrome.get(); chromes.push_back(std::move(chrome));
        pointer->plate.Insert(root, surfaces[5]);
        return pointer->confirmed = pointer->Update();
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
            if (!stopping && !fontReady && ++fontChecks <= 12) fontReady = font.Resolved();
            if (!stopping && !fontReady && fontChecks > 12) { Fail(E_FAIL); requested = false; stopping = true; }
            bool loaded = fontReady; for (bool value : ready) loaded &= value;
            if (!stopping && !loaded && GetTickCount64() - loadingStarted > 10000) {
                Fail(HRESULT_FROM_WIN32(ERROR_TIMEOUT)); requested = false; stopping = true;
            }
            unsigned visible = 0, styled = 0, pending = 0;
            if (!stopping) for (auto const& chrome : chromes) chrome->confirmed = chrome->Update();
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
                    if (!cell.inserted && loaded) { EnsurePlate(cell); cell.Insert(surfaces, font.family); }
                    unsigned childIndex = 0;
                    if (cell.inserted && cell.parent.Children().IndexOf(cell.canvas, childIndex) && childIndex == 1 &&
                        Hosting::ElementCompositionPreview::GetElementChildVisual(cell.canvas) == cell.visual && cell.ReconcileLabels() && EnsureChrome(cell)) ++styled;
                    else if (cell.inserted && !cell.parent.Children().IndexOf(cell.canvas, childIndex)) cell.unloaded = true;
                }
                ++it;
            }
            for (auto it = plates.begin(); it != plates.end();) {
                if (stopping || !VisualTreeHelper::GetParent((*it)->parent)) {
                    if ((*it)->Restore()) { it = plates.erase(it); continue; }
                }
                ++it;
            }
            for (auto it = chromes.begin(); it != chromes.end();) {
                if (stopping || !VisualTreeHelper::GetParent((*it)->root) || VisualTreeHelper::GetParent((*it)->bar) != (*it)->root) {
                    if ((*it)->Restore()) { it = chromes.erase(it); continue; }
                }
                ++it;
            }
            pending = visible > styled ? visible - styled : 0;
            const bool clean = stopping && cells.empty() && plates.empty() && chromes.empty();
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
                font.Clear(); candidates.clear(); started = false; owner = 0;
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
