import { ButtonItem, DialogButton, DropdownItem, ModalRoot, SliderField, ToggleField, findSP, Navigation } from "@decky/ui";
import { useEffect, useMemo, useState } from "react";
import { showModal } from "../navigation/showModal";
import { listInstalledGames } from "../launch/steamApi";
import { useI18n } from "../i18n";
import { DEFAULT_ARTWORK, type GameArtwork } from "../themes/artwork";
import { artworkAccess, loadArtwork, saveArtwork } from "../themes/artworkClient";
import { artworkImages, previewArtworkImage, artworkSourceLabel, artworkGameTitle } from "../themes/artworkImages";
import { recordUiEvent } from "../system/uiEvents";

function ArtworkEditor({ appId, closeModal }: { appId?: number; closeModal?: () => void }) {
  const { lang } = useI18n();
  const es = lang === "es";
  const games = useMemo(listInstalledGames, []);
  const [id, setId] = useState(appId ?? games[0]?.liveAppid ?? 0);
  const [draft, setDraft] = useState<GameArtwork>({ ...DEFAULT_ARTWORK });
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [failed, setFailed] = useState<string[]>([]);
  const images = useMemo(() => artworkImages(id), [id]);
  useEffect(() => {
    let active = true;
    setLoaded(false); setError(""); setFailed([]);
    void loadArtwork().then(() => {
      if (active) { setDraft({ ...(artworkAccess.get(id) ?? DEFAULT_ARTWORK) }); setLoaded(true); }
    }).catch(() => { if (active) setError(es ? "No se pudieron cargar las portadas." : "Could not load artwork."); });
    return () => { active = false; };
  }, [id, es]);
  const candidates = images.filter((x) => x.source !== "logo" && !failed.includes(x.url));
  const image = previewArtworkImage(draft, images, failed);
  const logo = images.find((x) => x.source === "logo" && !failed.includes(x.url))?.url;
  const title = artworkGameTitle(id, games.find((x) => x.liveAppid === id)?.name);
  const save = async (value: GameArtwork | null) => {
    setBusy(true); setError("");
    try { await saveArtwork(id, value); closeModal?.(); }
    catch { setError(es ? "No se pudo guardar. Inténtalo de nuevo." : "Could not save. Try again."); }
    finally { setBusy(false); }
  };
  const fail = (url: string) => setFailed((previous) => [...previous, url]);
  return <ModalRoot closeModal={busy ? undefined : closeModal} bDisableBackgroundDismiss={busy}>
    <div style={{ padding: 24, maxHeight: "80vh", overflowY: "auto", minWidth: 480 }}>
      <h2>{es ? "Editor de portadas" : "Cover editor"}</h2>
      {!appId && <DropdownItem label={es ? "Juego" : "Game"} selectedOption={id} rgOptions={games.map((g) => ({ data: g.liveAppid, label: g.name }))} onChange={(o) => setId(o.data)} disabled={busy} />}
      <div style={{ width: 200, height: 200, position: "relative", overflow: "hidden", borderRadius: 16, background: "#182231", margin: "16px auto" }}>
        {image && <img src={image} onError={() => fail(image)} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: `${draft.positionX}% ${draft.positionY}%` }} />}
        {draft.showLogo && logo && <img src={logo} onError={() => fail(logo)} style={{ position: "absolute", top: "27%", left: "11%", width: "78%", height: "36%", objectFit: "contain" }} />}
        {draft.showTitle && <div style={{ position: "absolute", bottom: 0, insetInline: 0, padding: 12, background: "#000a", color: "white" }}>{title}</div>}
      </div>
      <DropdownItem label={es ? "Imagen de Steam" : "Steam image"} selectedOption={draft.image ?? "auto"} disabled={!loaded || busy} rgOptions={[{ data: "auto", label: es ? "Automática" : "Automatic" }, ...candidates.map((x, i) => ({ data: x.url, label: `${artworkSourceLabel(x.source as Exclude<GameArtwork["source"], "auto">, es)} ${i + 1}` }))]} onChange={(o) => {
        const choice = candidates.find((x) => x.url === o.data);
        setDraft({ ...draft, source: choice ? choice.source as GameArtwork["source"] : "auto", image: choice?.url ?? null });
      }} />
      <SliderField label={es ? "Posición horizontal" : "Horizontal position"} value={draft.positionX} min={0} max={100} step={1} disabled={!loaded || busy} onChange={(positionX) => setDraft({ ...draft, positionX })} />
      <SliderField label={es ? "Posición vertical" : "Vertical position"} value={draft.positionY} min={0} max={100} step={1} disabled={!loaded || busy} onChange={(positionY) => setDraft({ ...draft, positionY })} />
      <ToggleField label="Logo" checked={draft.showLogo} disabled={!loaded || busy} onChange={(showLogo) => setDraft({ ...draft, showLogo })} />
      <ToggleField label={es ? "Título" : "Title"} checked={draft.showTitle} disabled={!loaded || busy} onChange={(showTitle) => setDraft({ ...draft, showTitle })} />
      {error && <p role="alert">{error}</p>}
      <DialogButton disabled={!loaded || busy || !id} onClick={() => void save({ ...draft, image: draft.image ? image ?? null : null })}>{es ? "Guardar" : "Save"}</DialogButton>
      <DialogButton disabled={!loaded || busy || !id} onClick={() => void save(null)}>{es ? "Restablecer" : "Reset"}</DialogButton>
      <DialogButton disabled={busy} onClick={closeModal}>{es ? "Cancelar" : "Cancel"}</DialogButton>
    </div>
  </ModalRoot>;
}
let editorOpen = false;
export function openGameArtworkEditor(appId?: number): boolean {
  if (editorOpen) return false;
  if (appId !== undefined && (!Number.isSafeInteger(appId) || appId <= 0)) return false;
  try {
    editorOpen = true;
    void loadArtwork().then(() => {
      const doc = findSP()?.document;
      const event = doc?.createEvent("CustomEvent");
      event?.initCustomEvent("pdc-duo-artwork-open", false, true, { appId, onClose: () => { editorOpen = false; } });
      if (doc && event && !doc.dispatchEvent(event)) { Navigation.CloseSideMenus(); return; }
      showModal(<ArtworkEditor appId={appId} />, window, { fnOnClose: () => { editorOpen = false; } });
    }).catch(() => {
      recordUiEvent("themes", "artwork_editor_failed", {}, false);
      showModal(<ArtworkEditor appId={appId} />, window, { fnOnClose: () => { editorOpen = false; } });
    });
    return true;
  }
  catch { editorOpen = false; recordUiEvent("themes", "artwork_editor_failed", {}, false); return false; }
}
export function GameArtworkEditorButton({ onOpen, disabled = false }: { onOpen?: () => void; disabled?: boolean }) {
  const { t } = useI18n();
  return <ButtonItem disabled={disabled} onClick={() => {
    if (onOpen) {
      onOpen();
      const deadline = Date.now() + 1000;
      const afterModalReturn = () => {
        const store = (window as unknown as { SteamUIStore?: { WindowStore?: { GamepadUIMainWindowInstance?: { MenuStore?: { GetOpenSideMenu?(): number } } } } }).SteamUIStore;
        const menu = store?.WindowStore?.GamepadUIMainWindowInstance?.MenuStore?.GetOpenSideMenu?.();
        if (menu === 2 || Date.now() >= deadline) openGameArtworkEditor();
        else requestAnimationFrame(afterModalReturn);
      };
      requestAnimationFrame(afterModalReturn);
    } else openGameArtworkEditor();
  }}>{t("artwork.contextMenu")}</ButtonItem>;
}
