import { Focusable, ModalRoot } from "@decky/ui";
import { FC, useLayoutEffect, useRef, useState } from "react";
import { LuBlocks, LuPencil } from "react-icons/lu";

import { FocusRoot } from "../components/FocusRoot";
import { useI18n } from "../i18n";
import { showModal } from "../navigation/showModal";
import { theme } from "../theme";
import { Block, ComposerBody } from "./ComposerEditor";
import { DrawBody, DrawingDraft } from "./DrawEditor";
import { PANEL_H, PANEL_W } from "./pixelFrames";
import { confirmDestructive } from "./SafeConfirm";

const SIDE_COLUMN = 400;
const CHROME_WIDTH = 160;
const CHROME_HEIGHT = 230;

type Session =
  | { kind: "draw"; draft: DrawingDraft; onSent: (id: string) => void }
  | { kind: "compose"; blocks: Block[]; onShow: (blocks: Block[]) => void };

function pitchFor(width: number, height: number, max: number): number {
  const byWidth = Math.floor((width - SIDE_COLUMN - CHROME_WIDTH) / PANEL_W);
  const byHeight = Math.floor((height - CHROME_HEIGHT) / PANEL_H);
  return Math.max(4, Math.min(max, byWidth, byHeight));
}

/** Steam sizes modals for dialogs; lift its width and height caps so the editor gets the screen. */
function unclamp(node: HTMLElement): void {
  const view = node.ownerDocument.defaultView;
  let element = node.parentElement;
  while (element && element !== node.ownerDocument.body && view?.getComputedStyle(element).position !== "fixed") {
    element.style.maxWidth = "none";
    element.style.maxHeight = "none";
    element = element.parentElement;
  }
}

const EditorModal: FC<{ session: Session; closeModal?: () => void }> = ({ session, closeModal }) => {
  const { t } = useI18n();
  const dirty = useRef(false);
  const root = useRef<HTMLDivElement>(null);
  const [pitch, setPitch] = useState(6);
  const draw = session.kind === "draw";

  useLayoutEffect(() => {
    const node = root.current;
    if (!node) return;
    unclamp(node);
    const view = node.ownerDocument.defaultView ?? window;
    setPitch(pitchFor(view.innerWidth, view.innerHeight, draw ? 10 : 8));
  }, [draw]);

  const close = () => closeModal?.();
  const leave = () => {
    if (!dirty.current) return close();
    confirmDestructive({ title: t("accessories.draw.discardTitle"), desc: t("accessories.draw.discardDesc"),
      confirmLabel: t("accessories.draw.discard"), cancelLabel: t("accessories.draw.keepEditing"), onConfirm: close });
  };

  return (
    <ModalRoot closeModal={leave} bAllowFullSize>
      <FocusRoot>
        <div ref={root}>
          <Focusable onCancelButton={leave} onCancelActionDescription={t("accessories.editor.back")}
            style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, color: theme.color.textPrimary }}>
              {draw ? <LuPencil size={22} color={theme.color.accent} /> : <LuBlocks size={22} color={theme.color.accent} />}
              <span style={{ fontSize: 22, fontWeight: 800 }}>{t(draw ? "accessories.editor.draw" : "accessories.compose.title")}</span>
              <span style={{ fontSize: theme.font.body, color: theme.color.textMuted, marginLeft: 8 }}>JSAUX PIXEL</span>
            </div>
            {session.kind === "draw" ? (
              <DrawBody initial={session.draft} pitch={pitch} closeModal={close}
                onDirty={() => { dirty.current = true; }} onSent={(id) => session.onSent(id)} />
            ) : (
              <ComposerBody initial={session.blocks} pitch={pitch} closeModal={close}
                onDirty={() => { dirty.current = true; }} onShow={(blocks) => session.onShow(blocks)} />
            )}
          </Focusable>
        </div>
      </FocusRoot>
    </ModalRoot>
  );
};

/** Opens an editor over Steam as a stretched modal: Decky's full-page routes do not render here. */
export function openEditor(session: Session): void {
  showModal(<EditorModal session={session} />, window);
}
