import { ModalRoot, showModal } from "@decky/ui";
import { useEffect, useRef, type FC } from "react";
import { LuImage } from "react-icons/lu";

import { FocusRoot } from "../../components/FocusRoot";
import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { ThemeImagePick, ThemeImagePicker, ThemeImageRequest } from "../steam/themeImages";
import { FilesTab } from "./FilesTab";
import { DimDialog, Empty, Sheet } from "./stationsParts";
import { useAmbient } from "./useAmbient";

export const ThemeImagePickerModal: FC<{ request: ThemeImageRequest; onDone: (pick: ThemeImagePick | null) => void; closeModal?: () => void }> = ({ request, onDone, closeModal }) => {
  const { t } = useI18n();
  const { runtime, snapshot } = useAmbient();
  const done = useRef(onDone);
  done.current = onDone;
  // Steam can dismiss the modal on its own (navigation, another modal); the theme still gets its answer.
  useEffect(() => () => done.current(null), []);
  const cancel = () => {
    onDone(null);
    closeModal?.();
  };
  const pickPhoto = async (photo: { ref: string }) => {
    const pick = await request.choose(photo.ref);
    if (!pick) return false;
    // Settle before closing: closing unmounts, and unmounting settles null.
    onDone(pick);
    closeModal?.();
    return true;
  };
  const header = (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
      <LuImage size={20} style={{ color: theme.color.accent, flexShrink: 0 }} />
      <span style={{ fontSize: 18, fontWeight: 700, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{request.title || t("ambient.pick.title")}</span>
    </div>
  );
  return <ModalRoot closeModal={cancel} onCancel={cancel} onEscKeypress={cancel} onOK={() => undefined} bAllowFullSize>
    <FocusRoot>
      <DimDialog />
      <Sheet>
        {runtime && snapshot?.state
          ? <FilesTab runtime={runtime} snapshot={snapshot} purpose="background" header={header} onClose={cancel} onPickPhoto={pickPhoto} />
          : <>{header}<Empty text={t(snapshot?.error ? "ambient.lib.loadFailed" : "ambient.lib.loading")} /></>}
      </Sheet>
    </FocusRoot>
  </ModalRoot>;
};

/** Opens the explorer over whatever Big Picture shows (a theme's Home) without touching the QAM. */
export const openThemeImagePicker: ThemeImagePicker = (request, signal) => new Promise((resolve) => {
  let settled = false;
  let modal: { Close(): void } | null = null;
  const finish = (pick: ThemeImagePick | null) => {
    if (settled) return;
    settled = true;
    signal.removeEventListener("abort", onAbort);
    resolve(pick);
  };
  const onAbort = () => {
    modal?.Close();
    finish(null);
  };
  signal.addEventListener("abort", onAbort);
  try {
    modal = showModal(<ThemeImagePickerModal request={request} onDone={finish} />, window);
  } catch {
    finish(null);
  }
});
