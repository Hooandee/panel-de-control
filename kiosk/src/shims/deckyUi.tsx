import type * as Decky from "@decky/ui/dist/index";
import { runningAppOverview } from "../runningGame";
import {
  ChangeEvent,
  Component,
  CSSProperties,
  FC,
  forwardRef,
  HTMLAttributes,
  ReactNode,
  useSyncExternalStore,
} from "react";

// Same export surface as @decky/ui for everything Panel imports; touch-first rendering.

type DeckyOnlyProps = {
  "flow-children"?: string;
  focusClassName?: string;
  focusWithinClassName?: string;
  noFocusRing?: boolean;
  onActivate?: (e: never) => void;
  onCancel?: (e: never) => void;
  onOKButton?: unknown;
  onSecondaryButton?: unknown;
  onOptionsButton?: unknown;
  onSecondaryActionDescription?: unknown;
  onOKActionDescription?: unknown;
  onOptionsActionDescription?: unknown;
  onCancelActionDescription?: unknown;
  onMenuButton?: unknown;
  onButtonDown?: unknown;
  onButtonUp?: unknown;
  onGamepadDirection?: unknown;
  onGamepadFocus?: unknown;
  onGamepadBlur?: unknown;
  actionDescriptionMap?: unknown;
  navRef?: unknown;
  navEntryPreferPosition?: unknown;
  autoFocus?: boolean;
};

function domProps<T extends DeckyOnlyProps>(props: T) {
  const {
    "flow-children": _flow,
    focusClassName: _fc,
    focusWithinClassName: _fwc,
    noFocusRing: _nfr,
    onActivate,
    onCancel: _oc,
    onOKButton: _ok,
    onSecondaryButton: _sb,
    onOptionsButton: _ob,
    onSecondaryActionDescription: _sad,
    onOKActionDescription: _oad,
    onOptionsActionDescription: _opd,
    onCancelActionDescription: _cad,
    onMenuButton: _mb,
    onButtonDown: _bd,
    onButtonUp: _bu,
    onGamepadDirection: _gd,
    onGamepadFocus: _gf,
    onGamepadBlur: _gb,
    actionDescriptionMap: _adm,
    navRef: _nr,
    navEntryPreferPosition: _nep,
    autoFocus: _af,
    ...rest
  } = props;
  return { rest, onActivate };
}

const FocusableKiosk = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & DeckyOnlyProps>(
  (props, ref) => {
    const { rest, onActivate } = domProps(props);
    const onClick = rest.onClick ?? (onActivate as HTMLAttributes<HTMLDivElement>["onClick"]);
    return <div ref={ref} {...rest} onClick={onClick} />;
  },
);

const PanelSectionKiosk: FC<{ title?: string; spinner?: boolean; children?: ReactNode }> = ({
  title,
  children,
}) => (
  <section className="k-section">
    {title && <div className="k-section-title">{title}</div>}
    {children}
  </section>
);

const PanelSectionRowKiosk: FC<{ children?: ReactNode }> = ({ children }) => (
  <div className="k-row">{children}</div>
);

interface ItemProps {
  label?: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  children?: ReactNode;
  disabled?: boolean;
  layout?: "below" | "inline";
  bottomSeparator?: "standard" | "thick" | "none";
  indentLevel?: number;
  highlightOnFocus?: boolean;
  childrenContainerWidth?: string;
  tooltip?: string;
}

const ItemFrame: FC<ItemProps & { control?: ReactNode; below?: ReactNode; onClick?: () => void }> = ({
  label,
  description,
  icon,
  disabled,
  control,
  below,
  onClick,
  indentLevel,
}) => (
  <div
    className={`k-item${disabled ? " is-disabled" : ""}`}
    style={indentLevel ? { paddingLeft: indentLevel * 14 } : undefined}
    onClick={disabled ? undefined : onClick}
  >
    <div className="k-item-head">
      {icon && <span className="k-item-icon">{icon}</span>}
      <div className="k-item-text">
        {label && <div className="k-item-label">{label}</div>}
        {description && <div className="k-item-desc">{description}</div>}
      </div>
      {control}
    </div>
    {below}
  </div>
);

const FieldKiosk: FC<ItemProps & { onClick?: () => void; onActivate?: () => void; focusable?: boolean }> = (props) => (
  <ItemFrame {...props} control={props.children} onClick={props.onClick ?? props.onActivate} />
);

const ToggleKiosk: FC<{ value: boolean; disabled?: boolean; onChange?(checked: boolean): void }> = ({
  value,
  disabled,
  onChange,
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={value}
    disabled={disabled}
    className={`k-switch${value ? " is-on" : ""}`}
    onClick={(e) => {
      e.stopPropagation();
      onChange?.(!value);
    }}
  >
    <span />
  </button>
);

const ToggleFieldKiosk: FC<ItemProps & { checked: boolean; onChange?(checked: boolean): void }> = (props) => (
  <ItemFrame
    {...props}
    onClick={() => props.onChange?.(!props.checked)}
    control={<ToggleKiosk value={props.checked} disabled={props.disabled} onChange={props.onChange} />}
  />
);

interface NotchLabel {
  notchIndex: number;
  label: string;
  value?: number;
}

const SliderFieldKiosk: FC<
  ItemProps & {
    value: number;
    min?: number;
    max?: number;
    step?: number;
    notchCount?: number;
    notchLabels?: NotchLabel[];
    notchTicksVisible?: boolean;
    showValue?: boolean;
    valueSuffix?: string;
    onChange?(value: number): void;
    className?: string;
  }
> = (props) => {
  const { value, min = 0, max = 100, step = 1, showValue, valueSuffix = "", notchLabels } = props;
  const fill = max > min ? ((value - min) / (max - min)) * 100 : 0;
  return (
    <ItemFrame
      {...props}
      control={showValue ? <span className="k-value">{`${value}${valueSuffix}`}</span> : undefined}
      below={
        <>
          <input
            className="k-range"
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            disabled={props.disabled}
            style={{ "--fill": `${fill}%` } as CSSProperties}
            onChange={(e: ChangeEvent<HTMLInputElement>) => props.onChange?.(Number(e.target.value))}
          />
          {notchLabels && notchLabels.length > 0 && (
            <div className="k-notches">
              {notchLabels.map((n) => (
                <span key={n.notchIndex}>{n.label}</span>
              ))}
            </div>
          )}
        </>
      }
    />
  );
};

const TextFieldKiosk: FC<
  HTMLAttributes<HTMLInputElement> & {
    label?: ReactNode;
    description?: ReactNode;
    disabled?: boolean;
    value?: string;
    onChange?: (e: ChangeEvent<HTMLInputElement>) => void;
    bIsPassword?: boolean;
    mustBeNumeric?: boolean;
    rangeMin?: number;
    rangeMax?: number;
    focusOnMount?: boolean;
    bShowClearAction?: boolean;
    bShowCopyAction?: boolean;
    bAlwaysShowClearAction?: boolean;
    inlineControls?: ReactNode;
    requiredLabel?: ReactNode;
    mustBeURL?: boolean;
    mustBeEmail?: boolean;
    tooltip?: string;
  }
> = ({
  label,
  description,
  disabled,
  value,
  onChange,
  bIsPassword,
  mustBeNumeric,
  rangeMin,
  rangeMax,
  inlineControls,
  focusOnMount: _fom,
  bShowClearAction: _sca,
  bShowCopyAction: _sco,
  bAlwaysShowClearAction: _asc,
  requiredLabel: _rl,
  mustBeURL: _mu,
  mustBeEmail: _me,
  tooltip: _t,
  ...rest
}) => (
  <label className="k-text">
    {label && <span className="k-item-label">{label}</span>}
    <span className="k-text-row">
      <input
        {...rest}
        type={bIsPassword ? "password" : mustBeNumeric ? "number" : "text"}
        min={rangeMin}
        max={rangeMax}
        disabled={disabled}
        value={value}
        onChange={onChange}
      />
      {inlineControls}
    </span>
    {description && <span className="k-item-desc">{description}</span>}
  </label>
);

type ButtonProps = HTMLAttributes<HTMLButtonElement> & DeckyOnlyProps & { disabled?: boolean };

const DialogButtonKiosk = forwardRef<HTMLButtonElement, ButtonProps>((props, ref) => {
  const { rest } = domProps(props);
  return <button ref={ref} type="button" className={`k-button ${rest.className ?? ""}`} {...rest} />;
});

const ButtonItemKiosk: FC<ItemProps & { onClick?(e: unknown): void; disabled?: boolean }> = ({ onClick, ...props }) => (
  <ItemFrame
    {...props}
    label={undefined}
    below={
      <button type="button" className="k-button k-button-wide" disabled={props.disabled} onClick={(e) => onClick?.(e)}>
        {props.children ?? props.label}
      </button>
    }
  />
);

const SpinnerKiosk: FC<{ style?: CSSProperties }> = ({ style }) => <span className="k-spinner" style={style} />;

class ErrorBoundaryKiosk extends Component<{ children?: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

interface ModalEntry {
  id: number;
  node: ReactNode;
  onClose?: () => void;
}
let modals: ModalEntry[] = [];
let modalSeq = 0;
const modalListeners = new Set<() => void>();
const emitModals = () => modalListeners.forEach((l) => l());

function showModalKiosk(
  node: ReactNode,
  _parent?: unknown,
  props?: { fnOnClose?: () => void },
): { Close: () => void; Update: (next: ReactNode) => void } {
  const id = ++modalSeq;
  const close = () => {
    if (!modals.some((m) => m.id === id)) return;
    modals = modals.filter((m) => m.id !== id);
    emitModals();
    props?.fnOnClose?.();
  };
  modals = [...modals, { id, node, onClose: close }];
  emitModals();
  return {
    Close: close,
    Update: (next) => {
      modals = modals.map((m) => (m.id === id ? { ...m, node: next } : m));
      emitModals();
    },
  };
}

export const ModalHost: FC = () => {
  const stack = useSyncExternalStore(
    (l) => {
      modalListeners.add(l);
      return () => modalListeners.delete(l);
    },
    () => modals,
  );
  return (
    <>
      {stack.map((m) => (
        <div key={m.id} className="k-modal-backdrop" onClick={m.onClose}>
          <div className="k-modal" onClick={(e) => e.stopPropagation()}>
            {m.node}
          </div>
        </div>
      ))}
    </>
  );
};

const ModalRootKiosk: FC<{
  children?: ReactNode;
  onCancel?(): void;
  closeModal?(): void;
  onOK?(): void;
  bOKDisabled?: boolean;
  bCancelDisabled?: boolean;
}> = ({ children, closeModal, onCancel }) => (
  <div className="k-modal-root">
    <button type="button" className="k-modal-close" aria-label="close" onClick={() => (onCancel ?? closeModal)?.()}>
      ×
    </button>
    {children}
  </div>
);

const ConfirmModalKiosk: FC<{
  strTitle?: ReactNode;
  strDescription?: ReactNode;
  strOKButtonText?: ReactNode;
  strCancelButtonText?: ReactNode;
  onOK?(): void;
  onCancel?(): void;
  closeModal?(): void;
}> = ({ strTitle, strDescription, strOKButtonText = "OK", strCancelButtonText, onOK, onCancel, closeModal }) => (
  <ModalRootKiosk closeModal={closeModal} onCancel={onCancel}>
    {strTitle && <div className="k-section-title">{strTitle}</div>}
    {strDescription && <div className="k-item-desc">{strDescription}</div>}
    <div className="k-modal-actions">
      {strCancelButtonText && (
        <DialogButtonKiosk onClick={() => { onCancel?.(); closeModal?.(); }}>{strCancelButtonText}</DialogButtonKiosk>
      )}
      <DialogButtonKiosk className="is-primary" onClick={() => { onOK?.(); closeModal?.(); }}>{strOKButtonText}</DialogButtonKiosk>
    </div>
  </ModalRootKiosk>
);

interface DropdownOption {
  data?: unknown;
  label: ReactNode;
  options?: DropdownOption[];
}

function flatOptions(options: DropdownOption[]): DropdownOption[] {
  return options.flatMap((o) => (o.options ? flatOptions(o.options) : [o]));
}

const DropdownKiosk: FC<{
  rgOptions: DropdownOption[];
  selectedOption: unknown;
  disabled?: boolean;
  onChange?(data: DropdownOption): void;
  strDefaultLabel?: string;
  menuLabel?: string;
  renderButtonValue?(element: ReactNode): ReactNode;
}> = ({ rgOptions, selectedOption, disabled, onChange, strDefaultLabel, menuLabel, renderButtonValue }) => {
  const options = flatOptions(rgOptions);
  const selected = options.find((o) => o.data === selectedOption);
  const shown = selected?.label ?? strDefaultLabel ?? "";
  const open = () => {
    const modal = showModalKiosk(
      <ModalRootKiosk closeModal={() => modal.Close()}>
        {menuLabel && <div className="k-section-title">{menuLabel}</div>}
        <div className="k-menu">
          {options.map((o, i) => (
            <button
              key={i}
              type="button"
              className={`k-menu-item${o.data === selectedOption ? " is-selected" : ""}`}
              onClick={() => {
                modal.Close();
                onChange?.(o);
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </ModalRootKiosk>,
    );
  };
  return (
    <button type="button" className="k-dropdown" disabled={disabled} onClick={open}>
      <span>{renderButtonValue ? renderButtonValue(shown) : shown}</span>
      <span className="k-chevron">⌄</span>
    </button>
  );
};

const DropdownItemKiosk: FC<ItemProps & Parameters<typeof DropdownKiosk>[0]> = (props) => (
  <ItemFrame {...props} control={<DropdownKiosk {...props} />} />
);

const staticClassesKiosk: Record<string, string> = new Proxy({} as Record<string, string>, {
  get: (_t, key) => `k-static-${String(key)}`,
});

const noop = () => {};
const NavigationKiosk = {
  Navigate: noop,
  NavigateBack: noop,
  NavigateToExternalWeb: noop,
  OpenQuickAccessMenu: noop,
  OpenMainMenu: noop,
  CloseSideMenus: noop,
};
const RouterKiosk = {
  get MainRunningApp() {
    return runningAppOverview();
  },
  Navigate: noop,
  CloseSideMenus: noop,
};
const QuickAccessTabKiosk = { Decky: 999 };
const NavEntryPositionPreferencesKiosk = { FIRST: 0, LAST: 1, MAINTAIN_X: 2, MAINTAIN_Y: 3, PREFERRED: 4 };

const findModuleExportKiosk = (): undefined => undefined;
const findModuleByExportKiosk = (): undefined => undefined;
const findSPKiosk = (): Window => window;
const getFocusNavControllerKiosk = (): null => null;
const getGamepadNavigationTreesKiosk = (): [] => [];

export const Focusable = FocusableKiosk as unknown as typeof Decky.Focusable;
export const PanelSection = PanelSectionKiosk as unknown as typeof Decky.PanelSection;
export const PanelSectionRow = PanelSectionRowKiosk as unknown as typeof Decky.PanelSectionRow;
export const Field = FieldKiosk as unknown as typeof Decky.Field;
export const Toggle = ToggleKiosk as unknown as typeof Decky.Toggle;
export const ToggleField = ToggleFieldKiosk as unknown as typeof Decky.ToggleField;
export const SliderField = SliderFieldKiosk as unknown as typeof Decky.SliderField;
export const TextField = TextFieldKiosk as unknown as typeof Decky.TextField;
export const DialogButton = DialogButtonKiosk as unknown as typeof Decky.DialogButton;
export const ButtonItem = ButtonItemKiosk as unknown as typeof Decky.ButtonItem;
export const Spinner = SpinnerKiosk as unknown as typeof Decky.Spinner;
export const ModalRoot = ModalRootKiosk as unknown as typeof Decky.ModalRoot;
export const ConfirmModal = ConfirmModalKiosk as unknown as typeof Decky.ConfirmModal;
export const Dropdown = DropdownKiosk as unknown as typeof Decky.Dropdown;
export const DropdownItem = DropdownItemKiosk as unknown as typeof Decky.DropdownItem;
export const showModal = showModalKiosk as unknown as typeof Decky.showModal;
export const staticClasses = staticClassesKiosk as unknown as typeof Decky.staticClasses;
export const Navigation = NavigationKiosk as unknown as typeof Decky.Navigation;
export const Router = RouterKiosk as unknown as typeof Decky.Router;
export const QuickAccessTab = QuickAccessTabKiosk as unknown as typeof Decky.QuickAccessTab;
export const NavEntryPositionPreferences = NavEntryPositionPreferencesKiosk as unknown as typeof Decky.NavEntryPositionPreferences;
export const findModuleExport = findModuleExportKiosk as unknown as typeof Decky.findModuleExport;
export const findModuleByExport = findModuleByExportKiosk as unknown as typeof Decky.findModuleByExport;
export const findSP = findSPKiosk as unknown as typeof Decky.findSP;
export const getFocusNavController = getFocusNavControllerKiosk as unknown as typeof Decky.getFocusNavController;
export const getGamepadNavigationTrees = getGamepadNavigationTreesKiosk as unknown as typeof Decky.getGamepadNavigationTrees;
export const ErrorBoundary = ErrorBoundaryKiosk as unknown as typeof Decky.ErrorBoundary;
export const Button = DialogButtonKiosk as unknown as typeof Decky.Button;
