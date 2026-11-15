#include "styler.h"
#include <shcore.h>
#include <shlwapi.h>
#undef GetCurrentTime
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Foundation.Numerics.h>
#include <winrt/Windows.Storage.Streams.h>
#include <winrt/Windows.UI.Composition.h>
#include <winrt/Windows.UI.Text.h>
#include <winrt/Windows.UI.Core.h>
#include <winrt/Windows.UI.Xaml.h>
#include <winrt/Windows.UI.Xaml.Controls.h>
#include <winrt/Windows.UI.Xaml.Data.h>
#include <winrt/Windows.UI.Xaml.Input.h>
#include <winrt/Windows.UI.Xaml.Hosting.h>
#include <winrt/Windows.UI.Xaml.Media.h>
#include "theme_style.h"
#include "font_resource.h"
#include <array>
#include <algorithm>
#include <cwctype>
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <optional>
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
std::atomic<bool> requested{false}, effectProbe{false};
std::atomic<ULONGLONG> lease{0}, generation{0};
std::atomic<DWORD> owner{0};
std::atomic<ThemeId> sessionTheme{ThemeId::None};
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
void RecordFont(UIElement const& element, FontFamily const& family, double size, unsigned role, unsigned kind) {
    auto name = to_string(family.Source());
    if (const auto fragment = name.rfind('#'); fragment != std::string::npos) name = name.substr(fragment + 1);
    if (name.empty() || name.size() >= TypeLength) return;
    for (char c : name) if (!TypeCharacter(c) && c != ' ' && c != '-' && c != ',') return;
    std::lock_guard lock(receiptGate);
    for (unsigned i = 0; i < receipt.fontCount; ++i)
        if (receipt.fonts[i].role == role && receipt.fonts[i].kind == kind && name == receipt.fonts[i].family) return;
    if (receipt.fontCount == MaxFontSamples) return;
    auto& sample = receipt.fonts[receipt.fontCount++];
    strcpy_s(sample.family, name.c_str()); sample.role = role; sample.kind = kind;
    sample.size = static_cast<float>(size); sample.opacity = static_cast<float>(element.Opacity());
    sample.visible = element.Visibility() == Visibility::Visible ? 1 : 0;
}
void RecordFonts(DependencyObject const& node, unsigned role, unsigned depth = 0) {
    if (!node || depth > 6) return;
    if (auto text = node.try_as<TextBlock>()) RecordFont(text, text.FontFamily(), text.FontSize(), role, 0);
    else if (auto icon = node.try_as<FontIcon>()) RecordFont(icon, icon.FontFamily(), icon.FontSize(), role, 1);
    for (int i = 0, count = VisualTreeHelper::GetChildrenCount(node); i < count; ++i)
        RecordFonts(VisualTreeHelper::GetChild(node, i), role, depth + 1);
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
    bool Same(IInspectable const& left, IInspectable const& right) const {
        if (left == right) return true;
        if (property != TextBlock::FontWeightProperty()) return false;
        auto a = left.try_as<Windows::Foundation::IReference<Windows::UI::Text::FontWeight>>();
        auto b = right.try_as<Windows::Foundation::IReference<Windows::UI::Text::FontWeight>>();
        return a && b && a.Value().Weight == b.Value().Weight;
    }
    void Assign(IInspectable const& value) {
        if (Same(element.GetValue(property), value)) return;
        if (assigned && !Same(element.ReadLocalValue(property), owned)) Capture();
        element.SetValue(property, value); owned = value; assigned = true; restoring = false; restored = false;
    }
    void Restore() {
        if (restored || !assigned) return;
        if (!restoring && !Same(element.ReadLocalValue(property), owned)) { restored = true; return; }
        restoring = true;
        if (binding) { element.ClearValue(property); element.SetBinding(property, binding); }
        else if (original == DependencyProperty::UnsetValue()) element.ClearValue(property);
        else element.SetValue(property, original);
        if (binding) {
            auto expression = element.GetBindingExpression(property);
            if (!expression || expression.ParentBinding() != binding) throw hresult_error(E_FAIL);
        } else if (!Same(element.ReadLocalValue(property), original)) throw hresult_error(E_FAIL);
        restored = true;
    }

};
void QueueObservedElement(FrameworkElement const& element) noexcept;
struct Label {
    TextBlock element{nullptr};
    std::unique_ptr<Property> foreground;
    std::unique_ptr<Property> font;
    bool icon = false, secondary = false;
    std::optional<std::int64_t> foregroundChanged, fontChanged, weightChanged, glyphChanged;
    std::unique_ptr<Property> weight;
    void Watch() {
        DependencyPropertyChangedCallback changed([](DependencyObject const& sender, DependencyProperty const&) noexcept {
            try { QueueObservedElement(sender.try_as<FrameworkElement>()); }
            catch (...) { Fail(to_hresult()); requested = false; }
        });
        foregroundChanged = element.RegisterPropertyChangedCallback(TextBlock::ForegroundProperty(), changed);
        fontChanged = element.RegisterPropertyChangedCallback(TextBlock::FontFamilyProperty(), changed);
        weightChanged = element.RegisterPropertyChangedCallback(TextBlock::FontWeightProperty(), changed);
        if (icon) glyphChanged = element.RegisterPropertyChangedCallback(TextBlock::TextProperty(), changed);
    }
    void Unwatch() {
        if (glyphChanged) { element.UnregisterPropertyChangedCallback(TextBlock::TextProperty(), *glyphChanged); glyphChanged.reset(); }
        if (weightChanged) { element.UnregisterPropertyChangedCallback(TextBlock::FontWeightProperty(), *weightChanged); weightChanged.reset(); }
        if (foregroundChanged) {
            element.UnregisterPropertyChangedCallback(TextBlock::ForegroundProperty(), *foregroundChanged);
            foregroundChanged.reset();
        }
        if (fontChanged) {
            element.UnregisterPropertyChangedCallback(TextBlock::FontFamilyProperty(), *fontChanged);
            fontChanged.reset();
        }
    }
};
bool IdentityTransform(Transform const& value) {
    if (!value) return true;
    auto origin = value.TransformPoint({0, 0});
    auto horizontal = value.TransformPoint({1, 0});
    auto vertical = value.TransformPoint({0, 1});
    return origin.X == 0 && origin.Y == 0 && horizontal.X == 1 && horizontal.Y == 0 && vertical.X == 0 && vertical.Y == 1;
}
void FollowNativeOpacity(UIElement const& source, UIElement const& target) {
    auto native = Hosting::ElementCompositionPreview::GetElementVisual(source);
    auto overlay = Hosting::ElementCompositionPreview::GetElementVisual(target);
    auto opacity = native.Compositor().CreateExpressionAnimation(L"native.Opacity");
    opacity.SetReferenceParameter(L"native", native);
    overlay.StartAnimation(L"Opacity", opacity);
}
KeyGlyph IdentifyKeyGlyph(DependencyObject const& node, unsigned depth = 0) {
    if (!node || depth > 6) return {KeyRole::Normal, false};
    FontFamily family{nullptr};
    if (auto text = node.try_as<TextBlock>()) family = text.FontFamily();
    else if (auto icon = node.try_as<FontIcon>()) family = icon.FontFamily();
    if (family) {
        auto familySource = family.Source();
        auto source = std::wstring_view(familySource);
        if (const auto fragment = source.rfind(L'#'); fragment != std::wstring_view::npos) source.remove_prefix(fragment + 1);
        if (source.find(L"Segoe Fluent Icons") != std::wstring_view::npos || source.find(L"Segoe MDL2 Assets") != std::wstring_view::npos || source == L"Emoji SIP Fluent Icons") {
            // Only native icon labels are inspected; ordinary key text and input fields are never read.
            auto glyph = node.try_as<TextBlock>() ? node.as<TextBlock>().Text() : node.as<FontIcon>().Glyph();
            if (glyph.size() == 1) {
                auto match = source == L"Emoji SIP Fluent Icons" ? RoleFromSipGlyph(glyph[0]) : RoleFromGlyph(glyph[0]);
                if (match.role != KeyRole::Normal) return match;
            }
        }
    }
    for (int i = 0, count = VisualTreeHelper::GetChildrenCount(node); i < count; ++i) {
        auto match = IdentifyKeyGlyph(VisualTreeHelper::GetChild(node, i), depth + 1);
        if (match.role != KeyRole::Normal) return match;
    }
    return {KeyRole::Normal, false};
}
struct Cell {
    Border face{nullptr};
    Grid parent{nullptr};
    FrameworkElement key{nullptr};
    Grid outer{nullptr};
    ContentControl content{nullptr};
    std::unique_ptr<Property> contentTransform;
    TranslateTransform pressedTransform;
    ThemeStyle const* style = &VelvetStyle;
    KeyRole role = KeyRole::Normal;
    bool latched = false;
    FontFamily font{nullptr};
    SolidColorBrush ink{nullptr}, soft{nullptr}, accent{nullptr}, pressedInk{nullptr}, enamel{nullptr}, focusedSoft{nullptr};
    Canvas canvas{nullptr};
    SpriteVisual visual{nullptr}, rune{nullptr}, glow{nullptr};
    ContainerVisual decoration{nullptr}, effects{nullptr};
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
    std::array<CompositionSurfaceBrush, 15> sources{nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};
    ScalarKeyFrameAnimation glowFade{nullptr};
    Vector3KeyFrameAnimation glowScale{nullptr};

    Brush LabelBrush(Label const& label) const {
        if (style->id == ThemeId::Terciopelo)
            return label.secondary ? soft : (pressed || focused) ? pressedInk : label.icon ? accent : ink;
        if (focused) return label.secondary ? focusedSoft : pressedInk;
        if (SignKey(role) || latched) return enamel;
        return label.secondary ? soft : ink;
    }
    void ReadFocus() {
        focused = false;
        if (auto control = key.try_as<Control>()) focused = control.FocusState() != FocusState::Unfocused;
        if (focused || !key.XamlRoot()) return;
        auto node = Windows::UI::Xaml::Input::FocusManager::GetFocusedElement(key.XamlRoot()).try_as<DependencyObject>();
        for (unsigned depth = 0; node && depth < 12; ++depth) {
            if (node == key) { focused = true; return; }
            node = VisualTreeHelper::GetParent(node);
        }
    }
    void Paint() {
        if (retiring || !inserted) return;
        if (style->id == ThemeId::LoboBlanco) latched = IdentifyKeyGlyph(content).latched;
        const unsigned index = FaceIndex(style->id, role, focused, pressed, hover, latched);
        brush.Source(sources[index]);
        if (contentTransform) {
            if (pressed && content.RenderTransform() != pressedTransform && !IdentityTransform(content.RenderTransform())) {
                contentTransform->Restore(); contentTransform.reset();
            } else if (pressed) contentTransform->Assign(pressedTransform);
            else contentTransform->Restore();
        }
        for (auto& label : labels) {
            label.foreground->Assign(LabelBrush(label));
            if (label.font) label.font->Assign(font);
            if (style->id == ThemeId::LoboBlanco && !label.icon) {
                if (!label.weight) label.weight = std::make_unique<Property>(label.element, TextBlock::FontWeightProperty());
                label.weight->Assign(box_value(Windows::UI::Text::FontWeights::Bold()));
            }
        }
    }
    void ShowEffectFrame() {
        if (retiring || !dust) return;
        dustStrip.StopAnimation(L"Offset"); dust.StopAnimation(L"Opacity");
        dustStrip.Offset({-4 * EffectWidth(), 0, 0}); dust.Opacity(1);
        if (glow) glow.Opacity(1);
    }
    void Strike() {
        if (retiring || !dust) return;
        dustStrip.StartAnimation(L"Offset", dustFrames);
        dust.StartAnimation(L"Opacity", dustFade);
        if (glow) { glow.StartAnimation(L"Opacity", glowFade); glow.StartAnimation(L"Scale", glowScale); }
    }
    void Geometry() {
        if (retiring || !visual || !parent) return;
        const bool visible = face.Visibility() == Visibility::Visible && face.ActualWidth() > 0 && face.ActualHeight() > 0;
        visual.Opacity(visible ? 1.f : 0.f);
        if (canvas) canvas.Visibility(visible ? Visibility::Visible : Visibility::Collapsed);
        if (dustCanvas) dustCanvas.Visibility(visible ? Visibility::Visible : Visibility::Collapsed);
        if (!visible) return;
        const auto origin = face.TransformToVisual(parent).TransformPoint({0, 0});
        visual.Offset({origin.X - style->outset, origin.Y - style->outset, 0});
        visual.Size({static_cast<float>(face.ActualWidth()) + 2 * style->outset,
                     static_cast<float>(face.ActualHeight()) + 2 * style->outset});
        if (dust) {
            const float bottom = style->id == ThemeId::Terciopelo ? .5f : role == KeyRole::Enter ? .3f : .42f;
            const float y = style->id == ThemeId::Terciopelo ? static_cast<float>(face.ActualHeight()) / 2 - 66 :
                static_cast<float>(face.ActualHeight()) * (1 - bottom) - EffectHeight();
            dust.Offset({origin.X + static_cast<float>(face.ActualWidth()) / 2 - EffectWidth()/2, origin.Y + y, 0});
        }
        if (rune) rune.Offset({origin.X + 12, origin.Y + 9, 0});
        if (glow) {
            glow.Offset({origin.X - 6, origin.Y - 6, 0});
            glow.Size({static_cast<float>(face.ActualWidth()) + 12, static_cast<float>(face.ActualHeight()) + 12});
            glow.CenterPoint({glow.Size().x/2, glow.Size().y/2, 0});
        }
    }
    float EffectWidth() const { return role == KeyRole::Enter ? style->enterWidth : style->effectWidth; }
    float EffectHeight() const { return role == KeyRole::Enter ? style->enterHeight : style->effectHeight; }
    void FindLabels(DependencyObject const& root, std::vector<TextBlock>& found, unsigned depth = 0) {
        if (depth > 6 || found.size() >= 12) return;
        if (auto text = root.try_as<TextBlock>()) found.push_back(text);
        for (int i = 0, n = VisualTreeHelper::GetChildrenCount(root); i < n; ++i)
            FindLabels(VisualTreeHelper::GetChild(root, i), found, depth + 1);
    }
    bool ReconcileLabels() {
        auto children = parent.Children();
        if (children.Size() != 4 || children.GetAt(0) != face || children.GetAt(1) != canvas || children.GetAt(3) != dustCanvas ||
            Hosting::ElementCompositionPreview::GetElementChildVisual(dustCanvas) != effects) return false;
        auto current = children.GetAt(2).try_as<ContentControl>();
        if (!current) return false;
        if (current != content) {
            if (contentTransform) contentTransform->Restore();
            contentTransform.reset(); content = current;
        }
        if (!contentTransform) {
            if (IdentityTransform(content.RenderTransform())) {
                contentTransform = std::make_unique<Property>(content, UIElement::RenderTransformProperty()); pressedTransform.Y(style->pressedOffset);
            }
        }
        std::vector<TextBlock> found;
        FindLabels(content, found);
        for (auto it = labels.begin(); it != labels.end();) {
            bool present = false;
            for (auto const& text : found) if (text == it->element) present = true;
            if (!present) {
                it->Unwatch();
                it->foreground->Restore(); if (it->font) it->font->Restore(); if (it->weight) it->weight->Restore();
                it = labels.erase(it);
            } else ++it;
        }
        for (auto const& text : found) {
            bool known = false;
            auto family = text.FontFamily().Source();
            auto familyName = std::wstring_view(family);
            if (const auto fragment = familyName.rfind(L'#'); fragment != std::wstring_view::npos)
                familyName.remove_prefix(fragment + 1);
            const bool icon = familyName == L"Xbox Fluent v2" ||
                familyName.find(L"Icon") != std::wstring_view::npos ||
                familyName.find(L"Symbol") != std::wstring_view::npos ||
                familyName.find(L"MDL2") != std::wstring_view::npos;
            for (auto& label : labels) if (label.element == text) {
                known = true;
                if (label.icon != icon) {
                    if (icon && label.font) { label.font->Restore(); label.font.reset(); if (label.weight) { label.weight->Restore(); label.weight.reset(); } }
                    else if (!icon) label.font = std::make_unique<Property>(text, TextBlock::FontFamilyProperty());
                    label.Unwatch(); label.icon = icon; label.Watch();
                }
            }
            if (known) continue;
            RecordFont(text, text.FontFamily(), text.FontSize(), 1, 0);
            labels.push_back({text, std::make_unique<Property>(text, TextBlock::ForegroundProperty()),
                icon ? nullptr : std::make_unique<Property>(text, TextBlock::FontFamilyProperty()), icon, false});
            labels.back().Watch();
        }
        double primarySize = 0;
        for (auto const& label : labels) if (!label.icon) primarySize = std::max(primarySize, label.element.FontSize());
        for (auto& label : labels) label.secondary = !label.icon && label.element.FontSize() + 1 < primarySize;
        Paint();
        for (auto const& label : labels) {
            Brush expected = LabelBrush(label);
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
    void Insert(std::array<LoadedImageSurface, 15> const& surfaces, FontFamily const& desiredFont) {
        auto children = parent.Children();
        if (children.Size() != 2 || children.GetAt(0) != face || !children.GetAt(1).try_as<ContentControl>()) {
            unloaded = true; return;
        }
        if (style->id == ThemeId::LoboBlanco) role = IdentifyKeyGlyph(children.GetAt(1)).role;
        canvas = Canvas(); canvas.Width(0); canvas.Height(0);
        canvas.HorizontalAlignment(HorizontalAlignment::Left); canvas.VerticalAlignment(VerticalAlignment::Top);
        canvas.IsHitTestVisible(false);
        auto compositor = Hosting::ElementCompositionPreview::GetElementVisual(parent).Compositor();
        for (unsigned i = 0; i < style->imageCount; ++i) {
            sources[i] = compositor.CreateSurfaceBrush(surfaces[i]); sources[i].Stretch(CompositionStretch::Fill);
        }
        brush = compositor.CreateNineGridBrush();
        brush.SetInsets(style->slice); brush.SetInsetScales(style->border / style->slice);
        brush.IsCenterHollow(false); brush.Source(sources[0]);
        visual = compositor.CreateSpriteVisual(); visual.Brush(brush);
        decoration = compositor.CreateContainerVisual(); decoration.Children().InsertAtBottom(visual);
        if (style->id == ThemeId::LoboBlanco && SignKey(role)) {
            rune = compositor.CreateSpriteVisual(); rune.Size({13,13});
            auto runeBrush = compositor.CreateSurfaceBrush(surfaces[9 + static_cast<unsigned>(role)]);
            runeBrush.Stretch(CompositionStretch::Uniform); rune.Brush(runeBrush);
            decoration.Children().InsertAtTop(rune);
        }
        dustCanvas = Canvas(); dustCanvas.Width(0); dustCanvas.Height(0);
        dustCanvas.HorizontalAlignment(HorizontalAlignment::Left); dustCanvas.VerticalAlignment(VerticalAlignment::Top); dustCanvas.IsHitTestVisible(false);
        effects = compositor.CreateContainerVisual();
        dust = compositor.CreateContainerVisual(); dust.Size({EffectWidth(), EffectHeight()}); dust.Opacity(0); dust.Clip(compositor.CreateInsetClip());
        dustStrip = compositor.CreateSpriteVisual(); dustStrip.Size({EffectWidth()*style->frames, EffectHeight()});
        auto dustBrush = compositor.CreateSurfaceBrush(surfaces[6]); dustBrush.Stretch(CompositionStretch::Fill);
        dustStrip.Brush(dustBrush); dust.Children().InsertAtTop(dustStrip);
        Hosting::ElementCompositionPreview::SetElementChildVisual(dustCanvas, effects);
        effects.Children().InsertAtTop(dust);
        if (style->id == ThemeId::LoboBlanco && SignKey(role)) {
            glow = compositor.CreateSpriteVisual(); glow.Opacity(0);
            auto gradient = compositor.CreateRadialGradientBrush();
            gradient.ColorStops().Append(compositor.CreateColorGradientStop(0, LoboGlowColors[static_cast<unsigned>(role)-1]));
            gradient.ColorStops().Append(compositor.CreateColorGradientStop(1, Color{0,0,0,0}));
            glow.Brush(gradient); effects.Children().InsertAtBottom(glow);
            glowFade = compositor.CreateScalarKeyFrameAnimation();
            glowFade.InsertKeyFrame(0,0); glowFade.InsertKeyFrame(.25f,1); glowFade.InsertKeyFrame(1,0);
            glowFade.Duration(std::chrono::milliseconds(420));
            glowScale = compositor.CreateVector3KeyFrameAnimation();
            auto ease = compositor.CreateCubicBezierEasingFunction({.2f,.7f},{.2f,1});
            glowScale.InsertKeyFrame(0,{.9f,.9f,1}); glowScale.InsertKeyFrame(.25f,{1,1,1},ease);
            glowScale.InsertKeyFrame(1,{1.08f,1.08f,1},ease); glowScale.Duration(std::chrono::milliseconds(420));
        }
        auto steps = compositor.CreateStepEasingFunction(style->frames - 1);
        steps.IsInitialStepSingleFrame(false); steps.IsFinalStepSingleFrame(true);
        dustFrames = compositor.CreateVector3KeyFrameAnimation();
        dustFrames.InsertKeyFrame(0, {0, 0, 0}); dustFrames.InsertKeyFrame(1, {-EffectWidth() * (style->frames - 1), 0, 0}, steps);
        dustFrames.Duration(std::chrono::milliseconds(role == KeyRole::Enter ? style->enterDuration : style->duration));
        dustFade = compositor.CreateScalarKeyFrameAnimation();
        auto linear = compositor.CreateLinearEasingFunction();
        dustFade.InsertKeyFrame(0, 1); dustFade.InsertKeyFrame(style->fadeStart, 1, linear); dustFade.InsertKeyFrame(1, 0, linear);
        dustFade.Duration(std::chrono::milliseconds(role == KeyRole::Enter ? style->enterDuration : style->duration)); Geometry();
        Hosting::ElementCompositionPreview::SetElementChildVisual(canvas, decoration);
        content = children.GetAt(1).as<ContentControl>(); font = desiredFont;
        RecordFonts(face, 0); RecordFonts(content, 1);
        children.InsertAt(1, canvas); inserted = true; children.Append(dustCanvas);
        FollowNativeOpacity(face, canvas);
        FollowNativeOpacity(face, dustCanvas);
        size = face.SizeChanged([this](auto const&, auto const&) noexcept { try { Geometry(); } catch (...) { unloaded = true; } });
        removed = key.Unloaded([this](auto const&, auto const&) noexcept { unloaded = true; });
        Pointer(UIElement::PointerPressedEvent(), 0); Pointer(UIElement::PointerReleasedEvent(), 1);
        Pointer(UIElement::PointerEnteredEvent(), 2); Pointer(UIElement::PointerExitedEvent(), 3);
        Pointer(UIElement::PointerCanceledEvent(), 3); Pointer(UIElement::PointerCaptureLostEvent(), 3);
        RoutedEventHandler got([this](auto const&, auto const&) noexcept { try { focused = true; Paint(); } catch (...) { Fail(to_hresult()); requested = false; } });
        RoutedEventHandler lost([this](auto const&, auto const&) noexcept { try { focused = false; Paint(); } catch (...) { Fail(to_hresult()); requested = false; } });
        gotFocus = key.GotFocus(got);
        lostFocus = key.LostFocus(lost);
        ReadFocus();
        Catalog(key); Catalog(parent);
        if (auto ancestor = VisualTreeHelper::GetParent(parent).try_as<FrameworkElement>()) Catalog(ancestor);
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
            attempt([&] { label.Unwatch(); });
            attempt([&] { label.foreground->Restore(); });
            if (label.font) attempt([&] { label.font->Restore(); });
            if (label.weight) attempt([&] { label.weight->Restore(); });
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
    Border frame{nullptr}; RectangleClip clip{nullptr};
    void Geometry() {
        if (!frame) { visual.Size({static_cast<float>(parent.ActualWidth()), static_cast<float>(parent.ActualHeight())}); return; }
        if (VisualTreeHelper::GetParent(frame) != parent || frame.Visibility() != Visibility::Visible) { visual.Opacity(0); return; }
        visual.Opacity(1);
        const auto origin = frame.TransformToVisual(parent).TransformPoint({0, 0});
        const auto width = static_cast<float>(frame.ActualWidth()), height = static_cast<float>(frame.ActualHeight());
        const auto radius = frame.CornerRadius();
        visual.Offset({origin.X, origin.Y, 0}); visual.Size({width, height});
        clip.Left(0); clip.Top(0); clip.Right(width); clip.Bottom(height);
        auto corner = [](double value) { const auto r = static_cast<float>(value); return Windows::Foundation::Numerics::float2{r, r}; };
        clip.TopLeftRadius(corner(radius.TopLeft)); clip.TopRightRadius(corner(radius.TopRight));
        clip.BottomLeftRadius(corner(radius.BottomLeft)); clip.BottomRightRadius(corner(radius.BottomRight));
    }
    void Insert(Grid const& value, LoadedImageSurface const& surface) {
        parent = value; canvas = Canvas(); canvas.Width(0); canvas.Height(0);
        canvas.HorizontalAlignment(HorizontalAlignment::Left); canvas.VerticalAlignment(VerticalAlignment::Top); canvas.IsHitTestVisible(false);
        auto compositor = Hosting::ElementCompositionPreview::GetElementVisual(parent).Compositor();
        visual = compositor.CreateSpriteVisual();
        auto brush = compositor.CreateSurfaceBrush(surface); brush.Stretch(CompositionStretch::Fill);
        visual.Brush(brush);
        if (frame) { clip = compositor.CreateRectangleClip(); visual.Clip(clip); }
        Geometry();
        Hosting::ElementCompositionPreview::SetElementChildVisual(canvas, visual);
        parent.Children().InsertAt(0, canvas);
        if (frame) FollowNativeOpacity(frame, canvas);
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
    SolidColorBrush clear{Color{0, 0, 0, 0}}, accent{nullptr};
    struct Entry { std::unique_ptr<Property> property; IInspectable value; };
    std::vector<Entry> properties;
    static Border FindFrame(Grid const& root) {
        Border frame{nullptr}; double area = 0;
        // In the observed build, the largest direct background Border owns the window outline.
        for (auto const& child : root.Children()) if (auto border = child.try_as<Border>()) {
            const auto candidateArea = border.ActualWidth() * border.ActualHeight();
            if (border.Visibility() == Visibility::Visible && border.Background() && candidateArea > area) {
                frame = border; area = candidateArea;
            }
        }
        return frame;
    }
    void Measure() {
        std::lock_guard lock(receiptGate);
        receipt.chromeCount = 0;
        auto record = [&](FrameworkElement const& element, unsigned kind, bool hasBackground, double radius) {
            if (receipt.chromeCount >= MaxChromeNodes) return;
            auto origin = element.TransformToVisual(root).TransformPoint({0, 0});
            receipt.chrome[receipt.chromeCount++] = {kind, hasBackground ? 1u : 0u, origin.X, origin.Y,
                static_cast<float>(element.ActualWidth()), static_cast<float>(element.ActualHeight()), static_cast<float>(radius)};
        };
        record(root, 0, !!root.Background(), root.CornerRadius().TopLeft);
        for (auto const& child : root.Children()) {
            if (auto border = child.try_as<Border>()) record(border, 2, !!border.Background(), border.CornerRadius().TopLeft);
            else if (auto grid = child.try_as<Grid>()) record(grid, 1, !!grid.Background(), grid.CornerRadius().TopLeft);
        }
    }
    void Set(FrameworkElement const& element, DependencyProperty const& dp, IInspectable const& value) {
        for (auto& entry : properties) if (entry.property->element == element && entry.property->property == dp) {
            entry.property->Assign(value); return;
        }
        if (properties.size() >= 256) throw hresult_error(E_BOUNDS);
        auto property = std::make_unique<Property>(element, dp);
        properties.push_back({std::move(property), value});
        properties.back().property->Assign(value);
    }
    void SetBackground(FrameworkElement const& element, DependencyProperty const& dp, Brush const& value) {
        // Transparent brushes receive pointer input; null backgrounds must stay null.
        if (element.GetValue(dp)) { Set(element, dp, value); return; }
        for (auto it = properties.begin(); it != properties.end(); ++it) {
            if (it->property->element == element && it->property->property == dp) {
                it->property->Restore(); properties.erase(it); return;
            }
        }
    }
    void StyleBar(DependencyObject const& node, unsigned depth = 0) {
        if (depth > 10) throw hresult_error(E_BOUNDS);
        if (node.try_as<WebView>() || node.try_as<TextBox>() || node.try_as<PasswordBox>()) return;
        if (auto panel = node.try_as<Panel>()) SetBackground(panel, Panel::BackgroundProperty(), clear);
        if (auto border = node.try_as<Border>()) SetBackground(border, Border::BackgroundProperty(), clear);
        if (auto control = node.try_as<Control>()) {
            SetBackground(control, Control::BackgroundProperty(), clear);
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
        if (!plate.frame || VisualTreeHelper::GetParent(plate.frame) != root || plate.frame.Visibility() != Visibility::Visible) {
            auto next = FindFrame(root);
            if (!next) { plate.visual.Opacity(0); return false; }
            plate.frame = next;
            FollowNativeOpacity(next, plate.canvas);
        }
        plate.Geometry();
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
    ULONGLONG epoch = 0, loadingStarted = 0, probeStarted = 0;
    bool probeAnimated = false, labelsQueued = false;
    std::array<FontResource, 3> fonts;
    FontFamily activeFont{nullptr};
    ThemeStyle const* style = &VelvetStyle;
    bool fontReady = false;
    unsigned fontChecks = 0;
    DispatcherTimer timer{nullptr}; event_token tick{};
    std::array<LoadedImageSurface, 15> surfaces{nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};
    std::array<event_token, 15> completions{};
    std::array<bool, 15> ready{};
    std::vector<std::unique_ptr<Cell>> cells;
    std::vector<weak_ref<FrameworkElement>> candidates;
    std::vector<std::unique_ptr<Plate>> plates;
    std::vector<std::unique_ptr<Chrome>> chromes;
    unsigned restored = 0, cleanupAttempts = 0;
    bool started = false;

    void Start(FrameworkElement const& anchor, ULONGLONG value) {
        if (started) return;
        epoch = value; loadingStarted = GetTickCount64(); probeStarted = 0; probeAnimated = false; labelsQueued = false; ready.fill(false); restored = 0; cleanupAttempts = 0; fontReady = false; fontChecks = 0;
        HMODULE module = nullptr;
        check_bool(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&KeyboardStyleId), &module));
        timer = DispatcherTimer(); timer.Interval(std::chrono::milliseconds(250));
        tick = timer.Tick([this](auto const&, auto const&) noexcept { Update(); }); timer.Start(); started = true;
        style = &StyleFor(sessionTheme.load());
        auto& primary = fonts[style->id == ThemeId::LoboBlanco ? 1 : 0];
        primary.Load(module, style->fontResource, style->fontFamily);
        activeFont = primary.family;
        if (style->fallbackFontResource) {
            fonts[2].Load(module, style->fallbackFontResource, style->fallbackFontFamily);
            auto source = std::wstring(primary.family.Source());
            source.erase(source.rfind(L", Segoe UI"));
            activeFont = FontFamily(source + L", " + std::wstring(fonts[2].family.Source()));
        }
        for (unsigned i = style->imageCount; i < ready.size(); ++i) ready[i] = true;
        auto dispatcher = anchor.Dispatcher();
        for (unsigned i = 0; i < style->imageCount; ++i) {
            auto resource = FindResourceW(module, MAKEINTRESOURCEW(style->images[i]), RT_RCDATA);
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
        auto ancestor = VisualTreeHelper::GetParent(parent);
        auto key = ancestor.try_as<FrameworkElement>();
        Grid outer{nullptr};
        if (!key || get_class_name(key) != KeyType) {
            outer = ancestor.try_as<Grid>();
            if (!outer || outer.Children().Size() != 1) return;
            key = VisualTreeHelper::GetParent(outer).try_as<FrameworkElement>();
            if (!key || get_class_name(key) != KeyType) return;
        }
        if (cells.size() >= 256) { Fail(E_BOUNDS); requested = false; return; }
        auto cell = std::make_unique<Cell>(); cell->style = style;
        cell->ink = SolidColorBrush(style->ink); cell->soft = SolidColorBrush(style->soft);
        cell->accent = SolidColorBrush(style->accent); cell->pressedInk = SolidColorBrush(style->pressed);
        cell->enamel = SolidColorBrush(style->enamel); cell->focusedSoft = SolidColorBrush(style->focusedSoft);
        cell->face = face; cell->parent = parent; cell->key = key; cell->outer = outer;
        cells.push_back(std::move(cell));
    }
    void RefreshLabels(FrameworkElement const& key, ULONGLONG value) {
        if (!started || labelsQueued || !requested || epoch != value || generation != value) return;
        labelsQueued = true;
        key.Dispatcher().RunAsync(Core::CoreDispatcherPriority::High, [this, value]() noexcept {
            if (epoch != value || generation != value) return;
            labelsQueued = false;
            if (!requested) return;
            try {
                for (auto& cell : cells) if (cell->inserted && !cell->retiring && !cell->unloaded)
                    cell->ReconcileLabels();
            } catch (...) { Fail(to_hresult()); requested = false; }
        });
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
        auto parent = VisualTreeHelper::GetChild(key, 0).try_as<Grid>();
        if (!parent) return;
        if (parent.Children().Size() == 1) parent = parent.Children().GetAt(0).try_as<Grid>();
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
        auto frame = Chrome::FindFrame(root);
        if (!frame) return false;
        auto chrome = std::make_unique<Chrome>(); chrome->root = root; chrome->bar = bar; chrome->plate.frame = frame; chrome->accent = SolidColorBrush(style->accent);
        auto pointer = chrome.get(); chromes.push_back(std::move(chrome));
        pointer->Measure();
        pointer->plate.Insert(root, surfaces[5]);
        return pointer->confirmed = pointer->Update();
    }
    void EnsurePlate(Cell const& cell) {
        if (style->id == ThemeId::LoboBlanco) return;
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
            if (!stopping && !fontReady && ++fontChecks <= 12) fontReady = fonts[style->id == ThemeId::LoboBlanco ? 1 : 0].Resolved() && (!style->fallbackFontResource || fonts[2].Resolved());
            if (!stopping && !fontReady && fontChecks > 12) { Fail(E_FAIL); requested = false; stopping = true; }
            bool loaded = fontReady; for (bool value : ready) loaded &= value;
            if (!stopping && !loaded && GetTickCount64() - loadingStarted > 10000) {
                Fail(HRESULT_FROM_WIN32(ERROR_TIMEOUT)); requested = false; stopping = true;
            }
            unsigned visible = 0, styled = 0, pending = 0;
            Cell* probeCell = nullptr;
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
                    (cell.outer ? (VisualTreeHelper::GetParent(cell.parent) != cell.outer || VisualTreeHelper::GetParent(cell.outer) != cell.key)
                                : VisualTreeHelper::GetParent(cell.parent) != cell.key)) {
                    const bool wasInserted = cell.inserted;
                    if (cell.Restore()) { if (wasInserted) ++restored; it = cells.erase(it); continue; }
                } else {
                    if (cell.inserted) cell.Geometry();
                    if (cell.face.XamlRoot() && cell.face.XamlRoot().IsHostVisible() &&
                           cell.face.ActualWidth() > 0 && cell.face.ActualHeight() > 0) {
                        if (!cell.inserted && loaded) { EnsurePlate(cell); cell.Insert(surfaces, activeFont); }
                        unsigned childIndex = 0;
                        if (cell.inserted && cell.parent.Children().IndexOf(cell.canvas, childIndex) && childIndex == 1 &&
                            Hosting::ElementCompositionPreview::GetElementChildVisual(cell.canvas) == cell.decoration && cell.ReconcileLabels() && EnsureChrome(cell)) {
                            ++styled; if (!probeCell) probeCell = &cell;
                        }
                        else if (cell.inserted && !cell.parent.Children().IndexOf(cell.canvas, childIndex)) cell.unloaded = true;
                    }
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
            if (!stopping && effectProbe && probeCell) {
                if (!probeStarted) { probeStarted = GetTickCount64(); probeCell->ShowEffectFrame(); }
                else if (!probeAnimated && GetTickCount64() - probeStarted >= 2000) { probeCell->Strike(); probeAnimated = true; }
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
                activeFont = nullptr; for (auto& font : fonts) font.Clear(); candidates.clear(); started = false; owner = 0;
            }
        } catch (...) { Fail(to_hresult()); requested = false; }
    }
};
Engine& Current() { static auto engine = new Engine; return *engine; }
void QueueObservedElement(FrameworkElement const& element) noexcept {
    if (!requested || !element) return;
    try {
        const auto value = generation.load();
        element.Dispatcher().RunAsync(Core::CoreDispatcherPriority::High, [element, value]() noexcept {
            try {
                if (!requested || generation != value) return;
                const auto thread = owner.load();
                if (thread && thread != GetCurrentThreadId()) return;
                auto key = element;
                const bool label = get_class_name(key) == L"Windows.UI.Xaml.Controls.TextBlock";
                if (label) {
                    for (unsigned depth = 0; key && get_class_name(key) != KeyType && depth < 12; ++depth)
                        key = VisualTreeHelper::GetParent(key).try_as<FrameworkElement>();
                }
                if (!key || get_class_name(key) != KeyType) return;
                if (label) Current().RefreshLabels(key, value);
                else Current().AddCandidate(key, value);
            } catch (...) {
                Fail(to_hresult()); requested = false;
                if (Current().started) Current().Update(); else owner = 0;
            }
        });
    } catch (...) { Fail(to_hresult()); requested = false; }
}
}

bool BeginStyleSession(ThemeId theme, bool probe) noexcept {
    if (!KnownTheme(theme)) return false;
    if (requested.exchange(true)) return false;
    if (owner.load()) { requested = false; return false; }
    sessionTheme = theme; effectProbe = probe;
    ++generation; lease = GetTickCount64() + 4000;
    std::lock_guard lock(receiptGate); receipt = {}; receipt.phase = StylePhase::Waiting;
    return true;
}
void RenewStyleLease() noexcept { if (requested) lease = GetTickCount64() + 4000; }
void StopStyleSession() noexcept {
    requested = false;
    if (!owner.load()) {
        std::lock_guard lock(receiptGate);
        if (!receipt.keyCount && !receipt.styledKeys && !receipt.pendingKeys) {
            receipt.phase = StylePhase::Idle; receipt.styleResult = S_OK;
        }
    }
}
void ObserveStyle(IXamlDiagnostics* diagnostics, InstanceHandle handle) noexcept {
    if (!requested || !diagnostics) return;
    try {
        IInspectable object{nullptr};
        check_hresult(diagnostics->GetIInspectableFromHandle(handle, reinterpret_cast<::IInspectable**>(put_abi(object))));
        QueueObservedElement(object.try_as<FrameworkElement>());
    } catch (...) { Fail(to_hresult()); requested = false; }
}

void ReadStyleSession(Report& report) noexcept {
    std::lock_guard lock(receiptGate);
    report.appliedTheme = receipt.phase == StylePhase::Applied ? sessionTheme.load() : ThemeId::None;
    report.phase = receipt.phase; report.keyCount = receipt.keyCount; report.styledKeys = receipt.styledKeys;
    report.restoredKeys = receipt.restoredKeys; report.pendingKeys = receipt.pendingKeys;
    report.styleResult = receipt.styleResult; report.stateCount = receipt.stateCount;
    memcpy(report.states, receipt.states, sizeof(receipt.states));
    report.fontCount = receipt.fontCount;
    memcpy(report.fonts, receipt.fonts, sizeof(receipt.fonts));
    report.chromeCount = receipt.chromeCount;
    memcpy(report.chrome, receipt.chrome, sizeof(receipt.chrome));
}
}
