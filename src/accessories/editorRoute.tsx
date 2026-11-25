import { ModalRoot, Navigation, QuickAccessTab } from "@decky/ui";
import { FC, useCallback, useMemo, useRef } from "react";

import { FocusRoot } from "../components/FocusRoot";
import { useI18n } from "../i18n";
import { showModal } from "../navigation/showModal";
import { Block, ComposerBody } from "./ComposerEditor";
import { DrawBody, DrawingDraft } from "./DrawEditor";
import { EditorContext, EditorControls } from "./editorControls";
import { confirmDestructive } from "./SafeConfirm";

type Session =
  | { kind: "draw"; draft: DrawingDraft; onSent: (id: string) => void }
  | { kind: "compose"; blocks: Block[]; onShow: (blocks: Block[]) => void };

// Steam pins every dialog in its main window to 660 px, even a full-size one, which cut the
// editors off. The class lifts that cap for these dialogs only; the shell sizes itself.
const MODAL_CLASS = "pdc-accessory-editor";
const STYLE_ID = "pdc-accessory-editor-style";
function ensureModalStyle(doc: Document) {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `.${MODAL_CLASS} > .DialogContent { width: auto !important; max-width: 96vw; }`;
  doc.head.appendChild(style);
}

const EditorModal: FC<{ session: Session; closeModal?: () => void }> = ({ session, closeModal }) => {
  const { t } = useI18n();
  const dirty = useRef(false);
  const closed = useRef(false);
  const asking = useRef(false);
  const root = useRef<HTMLDivElement | null>(null);

  const close = useCallback(() => {
    if (closed.current) return;
    closed.current = true;
    closeModal?.();
  }, [closeModal]);

  // ModalRoot is the only B handler: a second one on the content ran this twice and stacked
  // two confirmations, or closed the editor under the one it had just opened.
  const leave = useCallback(() => {
    if (closed.current || asking.current) return;
    if (!dirty.current) return close();
    asking.current = true;
    confirmDestructive(
      { title: t("accessories.draw.discardTitle"), desc: t("accessories.draw.discardDesc"),
        confirmLabel: t("accessories.draw.discard"), cancelLabel: t("accessories.draw.keepEditing"), onConfirm: close },
      root.current?.ownerDocument.defaultView ?? window,
      () => { asking.current = false; },
    );
  }, [close, t]);

  const controls = useMemo<EditorControls>(() => ({ close, leave, markDirty: () => { dirty.current = true; } }), [close, leave]);
  const attach = useCallback((element: HTMLDivElement | null) => {
    root.current = element;
    if (element) ensureModalStyle(element.ownerDocument);
  }, []);

  return (
    <ModalRoot closeModal={leave} bAllowFullSize modalClassName={MODAL_CLASS}>
      <FocusRoot>
        <div ref={attach}>
          <EditorContext.Provider value={controls}>
            {session.kind === "draw"
              ? <DrawBody initial={session.draft} onSent={session.onSent} />
              : <ComposerBody initial={session.blocks} onShow={session.onShow} />}
          </EditorContext.Provider>
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

let openEditorHandle: { Close: () => void } | null = null;

/** Opens an editor over Steam and, once it closes, brings the quick access menu back where it was. */
export function openEditor(session: Session): void {
  Navigation.CloseSideMenus();
  const handle = showModal(<EditorModal session={session} />, mainWindow(), {
    fnOnClose: () => {
      if (openEditorHandle === handle) openEditorHandle = null;
      Navigation.OpenQuickAccessMenu(QuickAccessTab.Decky);
    },
  });
  openEditorHandle = handle;
}

/** On unload: an editor left open outlives the plugin, dead, and keeps the gamepad focus. */
export function closeAccessoryEditor(): void {
  const handle = openEditorHandle;
  openEditorHandle = null;
  try {
    handle?.Close();
  } catch {
    /* Steam already dropped the dialog */
  }
}
