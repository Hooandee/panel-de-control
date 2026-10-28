import { ButtonItem, DialogButton, ModalRoot, Navigation, findSP } from '@decky/ui';
import { useI18n } from '../i18n';
import { showModal } from '../navigation/showModal';
import { recordUiEvent } from '../system/uiEvents';

function DockEditorUnavailable({ es, closeModal }: { es: boolean; closeModal?: () => void }) {
  return <ModalRoot closeModal={closeModal}>
    <p role="alert">{es ? 'No se pudo abrir el editor del Dock. Comprueba que DUO esté activo y actualizado.' : 'Could not open the Dock editor. Check that DUO is active and up to date.'}</p>
    <DialogButton onClick={closeModal}>{es ? 'Cerrar' : 'Close'}</DialogButton>
  </ModalRoot>;
}

let editorOpen = false;
export function openDuoDockEditor(es: boolean): boolean {
  if (editorOpen) return false;
  try {
    const doc = findSP()?.document;
    const event = doc?.createEvent('CustomEvent');
    let closed = false;
    event?.initCustomEvent('pdc-duo-dock-open', false, true, { onClose: () => {
      if (closed) return;
      closed = true;
      editorOpen = false;
      recordUiEvent('themes', 'duo_dock_editor_closed', {}, true);
    } });
    editorOpen = true;
    if (doc && event && !doc.dispatchEvent(event)) {
      Navigation.CloseSideMenus();
      recordUiEvent('themes', 'duo_dock_editor_opened', {}, true);
      return true;
    }
  } catch {}
  editorOpen = false;
  recordUiEvent('themes', 'duo_dock_editor_failed', {}, false);
  showModal(<DockEditorUnavailable es={es} />, window);
  return false;
}

export function DuoDockEditorButton({ onOpen, disabled = false }: { onOpen?: () => void; disabled?: boolean }) {
  const { lang } = useI18n();
  const es = lang === 'es';
  return <ButtonItem disabled={disabled} onClick={() => {
    if (!onOpen) { openDuoDockEditor(es); return; }
    onOpen();
    const deadline = Date.now() + 1000;
    const afterModalReturn = () => {
      const store = (window as unknown as { SteamUIStore?: { WindowStore?: { GamepadUIMainWindowInstance?: { MenuStore?: { GetOpenSideMenu?(): number } } } } }).SteamUIStore;
      const menu = store?.WindowStore?.GamepadUIMainWindowInstance?.MenuStore?.GetOpenSideMenu?.();
      if (menu === 2 || Date.now() >= deadline) openDuoDockEditor(es);
      else requestAnimationFrame(afterModalReturn);
    };
    requestAnimationFrame(afterModalReturn);
  }}>{es ? 'Personalizar Dock' : 'Customize Dock'}</ButtonItem>;
}
