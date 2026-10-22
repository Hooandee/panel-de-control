import { Focusable, Navigation } from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import { LuBlocks, LuPencil } from "react-icons/lu";

import { FocusRoot } from "../components/FocusRoot";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Block, ComposerBody } from "./ComposerEditor";
import { DrawBody, DrawingDraft } from "./DrawEditor";
import { PANEL_H, PANEL_W } from "./pixelFrames";
import { confirmDestructive } from "./SafeConfirm";

export const EDITOR_ROUTE = "/panel-de-control/accessories-editor";
const SIDE_COLUMN = 300;
const CHROME_HEIGHT = 190;

type Session =
  | { kind: "draw"; draft: DrawingDraft; onSent: (id: string) => void }
  | { kind: "compose"; blocks: Block[]; onShow: (blocks: Block[]) => void };

let session: Session | null = null;

/** Full-page editors: Steam modals stay ~620 px wide, too small for a comfortable canvas. */
export function openEditor(next: Session): void {
  session = next;
  Navigation.CloseSideMenus();
  Navigation.Navigate(EDITOR_ROUTE);
}

function pitchFor(width: number, height: number, max: number): number {
  const byWidth = Math.floor((width - SIDE_COLUMN - 80) / PANEL_W);
  const byHeight = Math.floor((height - CHROME_HEIGHT) / PANEL_H);
  return Math.max(4, Math.min(max, byWidth, byHeight));
}

export const EditorPage: FC = () => {
  const { t } = useI18n();
  const [current] = useState(session);
  const dirty = useRef(false);
  const root = useRef<HTMLDivElement>(null);
  const [pitch, setPitch] = useState(6);

  useEffect(() => {
    const view = root.current?.ownerDocument.defaultView ?? window;
    const measure = () => setPitch(pitchFor(view.innerWidth, view.innerHeight, current?.kind === "draw" ? 11 : 9));
    measure();
    view.addEventListener("resize", measure);
    return () => view.removeEventListener("resize", measure);
  }, [current?.kind]);

  const close = () => {
    session = null;
    Navigation.NavigateBack();
  };
  const leave = () => {
    if (!dirty.current) return close();
    confirmDestructive({ title: t("accessories.draw.discardTitle"), desc: t("accessories.draw.discardDesc"),
      confirmLabel: t("accessories.draw.discard"), cancelLabel: t("accessories.draw.keepEditing"), onConfirm: close });
  };

  if (!current) {
    return <div style={{ padding: 60, color: theme.color.textMuted }}>{t("accessories.editor.gone")}</div>;
  }
  const draw = current.kind === "draw";
  return (
    <div ref={root} style={{ height: "100%", boxSizing: "border-box", paddingTop: 56, paddingLeft: 40, paddingRight: 40,
      background: `radial-gradient(120% 70% at 30% 0%, rgba(${theme.color.accentRgb},0.16), ${theme.color.surface} 70%)` }}>
      <FocusRoot>
        <Focusable onCancelButton={leave} onCancelActionDescription={t("accessories.editor.back")}
          style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: theme.color.textPrimary }}>
            {draw ? <LuPencil size={22} color={theme.color.accent} /> : <LuBlocks size={22} color={theme.color.accent} />}
            <span style={{ fontSize: 24, fontWeight: 800 }}>{t(draw ? "accessories.editor.draw" : "accessories.compose.title")}</span>
            <span style={{ fontSize: theme.font.body, color: theme.color.textMuted, marginLeft: 8 }}>JSAUX PIXEL</span>
          </div>
          {draw ? (
            <DrawBody initial={current.draft} pitch={pitch} closeModal={close}
              onDirty={() => { dirty.current = true; }} onSent={(id) => { current.onSent(id); }} />
          ) : (
            <ComposerBody initial={current.blocks} pitch={pitch} closeModal={close}
              onDirty={() => { dirty.current = true; }} onShow={(blocks) => current.onShow(blocks)} />
          )}
        </Focusable>
      </FocusRoot>
    </div>
  );
};
