import { CSSProperties, FC, ReactNode } from "react";
import { Focusable, ModalRoot } from "@decky/ui";

import { theme } from "../../theme";
import { FocusRoot } from "../FocusRoot";

const ICON_TILE = 56;

/** Full-size notice: a centred 420px column for an icon, a big title, a body and stacked actions. */
export const NoticeDialog: FC<{ closeModal?: () => void; centered?: boolean; children: ReactNode }> = ({ closeModal, centered, children }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          ...(centered && { alignItems: "center", textAlign: "center" }),
          gap: theme.space.md,
          maxWidth: 420,
          margin: "0 auto",
          padding: theme.space.lg,
        }}
      >
        {children}
      </div>
    </FocusRoot>
  </ModalRoot>
);

export const NoticeHeader: FC<{ children: ReactNode }> = ({ children }) => (
  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.xs }}>{children}</div>
);

export const NoticeIcon: FC<{ background: string; outline?: string; children: ReactNode }> = ({ background, outline, children }) => (
  <div
    style={{
      width: ICON_TILE,
      height: ICON_TILE,
      borderRadius: theme.radius.md,
      background,
      display: "grid",
      placeItems: "center",
      ...(outline && { boxShadow: `inset 0 0 0 1px ${outline}` }),
    }}
  >
    {children}
  </div>
);

export const NoticeTitle: FC<{ centered?: boolean; children: ReactNode }> = ({ centered, children }) => (
  <div style={{ fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary, ...(centered && { textAlign: "center" }) }}>{children}</div>
);

export const NoticeActions: FC<{ style?: CSSProperties; children: ReactNode }> = ({ style, children }) => (
  <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, ...style }}>{children}</Focusable>
);

export const NoticeFootnote: FC<{ children: ReactNode }> = ({ children }) => (
  <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, textAlign: "center" }}>{children}</div>
);
