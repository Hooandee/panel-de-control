import { CSSProperties, FC, ReactNode, useRef } from "react";
import { Focusable } from "@decky/ui";

interface Props {
  onPress: () => void | Promise<void>;
  disabled?: boolean;
  pressed?: boolean;
  expanded?: boolean;
  label?: string;
  style?: CSSProperties;
  children: ReactNode;
}

export const QamAction: FC<Props> = ({
  onPress,
  disabled = false,
  pressed,
  expanded,
  label,
  style,
  children,
}) => {
  const locked = useRef(false);
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
      aria-pressed={pressed}
      aria-expanded={expanded}
      onActivate={press}
      onClick={press}
      style={style}
    >
      {children}
    </Focusable>
  );
};
