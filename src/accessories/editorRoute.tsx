import { Focusable, ModalRoot, Navigation, showModal } from "@decky/ui";
import { FC, useRef } from "react";
import { LuBlocks, LuPencil } from "react-icons/lu";

import { FocusRoot } from "../components/FocusRoot";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Block, ComposerBody } from "./ComposerEditor";
import { DrawBody, DrawingDraft } from "./DrawEditor";
import { confirmDestructive } from "./SafeConfirm";

// Steam keeps modals about 620 px wide whatever is asked, so the editors are laid out to fit it.
const EDITOR_PITCH = 5;

type Session =
  | { kind: "draw"; draft: DrawingDraft; onSent: (id: string) => void }
  | { kind: "compose"; blocks: Block[]; onShow: (blocks: Block[]) => void };

const EditorModal: FC<{ session: Session; closeModal?: () => void }> = ({ session, closeModal }) => {
  const { t } = useI18n();
  const dirty = useRef(false);
  const draw = session.kind === "draw";
  const pitch = EDITOR_PITCH;

  const close = () => closeModal?.();
  const leave = () => {
    if (!dirty.current) return close();
    confirmDestructive({ title: t("accessories.draw.discardTitle"), desc: t("accessories.draw.discardDesc"),
      confirmLabel: t("accessories.draw.discard"), cancelLabel: t("accessories.draw.keepEditing"), onConfirm: close });
  };

  return (
    <ModalRoot closeModal={leave} bAllowFullSize>
      <FocusRoot>
        <div>
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

interface SteamWindows {
  SteamUIStore?: { WindowStore?: { SteamUIWindows?: { m_BrowserWindow?: Window }[] } };
}

/** Steam's main window: the quick access menu's own window is too narrow for the canvas. */
function mainWindow(): Window {
  return (window as unknown as SteamWindows).SteamUIStore?.WindowStore?.SteamUIWindows?.[0]?.m_BrowserWindow ?? window;
}

/** Opens an editor over Steam as a stretched modal: Decky's full-page routes do not render here. */
export function openEditor(session: Session): void {
  Navigation.CloseSideMenus();
  showModal(<EditorModal session={session} />, mainWindow());
}
