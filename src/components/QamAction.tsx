import { CSSProperties, FC, ReactNode, useRef } from "react";
import { Focusable } from "@decky/ui";

interface Props {
  onPress: () => void | Promise<void>;
  disabled?: boolean;
  pressed?: boolean;
  checked?: boolean;
  expanded?: boolean;
  label?: string;
  style?: CSSProperties;
  children: ReactNode;
}

export const QamAction: FC<Props> = ({
  onPress,
  disabled = false,
  pressed,
  checked,
  expanded,
  label,
  style,
  children,
}) => {
  const locked = useRef(false);
  const isCheckbox = checked !== undefined;
  const press = () => {
    if (disabled || locked.current) return;
    locked.current = true;
    try {
      const result = onPress();
      void Promise.resolve(result).then(
        () => queueMicrotask(() => { locked.current = false; }),
        () => queueMicrotask(() => { locked.current = false; }),
      );
    } catch (error) {
      locked.current = false;
      throw error;
    }
  };

  if (disabled) {
    return (
      <span aria-hidden="true" style={style}>
        {children}
      </span>
    );
  }

  return (
    <Focusable
      aria-label={label}
      aria-pressed={isCheckbox ? undefined : pressed}
      aria-checked={checked}
      aria-expanded={expanded}
      role={isCheckbox ? "checkbox" : undefined}
      onActivate={press}
      onClick={press}
      style={style}
    >
      {children}
    </Focusable>
  );
};
