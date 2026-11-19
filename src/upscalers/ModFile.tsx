import { openFilePicker } from "@decky/api";
import { useEffect, useState, type FC } from "react";

import { addUpscalerMod, getUpscalerModCandidates, removeUpscalerMod } from "../api";
import { useI18n } from "../i18n";
import { upscalerErrorCode } from "./errorCode";
import { ListCard, ListRow, Note } from "./parts";
import type { GameDetail, GameMod } from "./types";
import { cancelUserFileWatch, downloadMod, MOD_WATCH, onUserFileWatch, watchingFor } from "./userFileWatch";

const EXTENSIONS = ["zip", "7z", "rar"];
const WIKI_PAGE = "https://github.com/optiscaler/OptiScaler/wiki/";

/** The OptiScaler wiki names the mod in its page title: «Elden-Ring-(ERSS‐FG)» → «ERSS-FG». */
export const wikiModName = (page: string | null | undefined): string | null => {
  const named = page?.match(/\(([^()]+)\)$/)?.[1];
  return named ? named.replace(/[‐‑–]/g, "-") : null;
};

const errorKey = (code: string) => code === "busy" ? "up.error.busy"
  : code === "mod_conflict" ? "up.error.mod_conflict"
  : code === "mod_layout" ? "up.error.mod_layout"
  : code === "mod_unsafe_archive" || code === "mod_too_large" || code === "mod_too_many_files" ? "up.error.mod_unsafe"
  : "up.error.mod_unreadable";

/** A mod the user brings for this game, installed beside the exe with OptiScaler. Games the wiki says need one get the
 *  card with Download and Choose file; any other game gets a single row to add one. */
export const ModFile: FC<{
  appid: string;
  mod: GameMod | null;
  needed: boolean;
  name: string | null;
  /** Where to download it: a known free download, else the wiki entry that names it. */
  download: string | null;
  disabled?: boolean;
  onDetail: (detail: GameDetail) => void;
  /** Present while the upscaler is installed without this mod (or with a removed one): puts it in now. */
  onApply?: () => void;
}> = ({ appid, mod, needed, name, download, disabled = false, onDetail, onApply }) => {
  const { t } = useI18n();
  const [folder, setFolder] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(() => watchingFor(appid, MOD_WATCH));

  useEffect(() => onUserFileWatch((event) => {
    if (event.appid !== appid || event.dependency !== MOD_WATCH) return;
    setWaiting(event.type === "watching");
    if (event.type === "adopted") onDetail(event.detail);
    if (event.type === "failed") setError(t(errorKey(event.code)));
  }), [appid, onDetail, t]);

  useEffect(() => {
    let live = true;
    getUpscalerModCandidates(appid).then((result) => { if (live) setFolder(result.folder); }).catch(() => undefined);
    return () => { live = false; };
  }, [appid]);

  const run = async (action: () => Promise<GameDetail>) => {
    setBusy(true);
    setError(null);
    try {
      onDetail(await action());
    } catch (failure) {
      setError(t(errorKey(upscalerErrorCode(failure))));
    } finally {
      setBusy(false);
    }
  };
  const pick = async () => {
    const picked = await openFilePicker(0 as never, folder ?? "/home", true, true, undefined, EXTENSIONS).catch(() => null);
    if (picked?.realpath) await run(() => addUpscalerMod(appid, picked.realpath));
  };
  const off = disabled || busy;
  const present = mod && !mod.removed ? mod : null;

  if (!needed && !mod) {
    return (
      <>
        <ListRow label={t("up.mod.add")} chevron disabled={off} busy={busy} onPress={() => void pick()} />
        {error && <Note tone="warn">{error}</Note>}
      </>
    );
  }

  const caption = mod?.removed ? t("up.mod.removing")
    : present && !present.applied ? t("up.mod.pending")
    : !present && needed ? t("up.mod.required")
    : undefined;

  return (
    <>
      <ListCard>
        <ListRow first label={name ? t("up.mod.named", { name }) : t("up.mod.title")}
          detail={present?.filename ?? t("up.userFile.missing")} caption={caption} busy={busy} />
        {mod && !mod.applied && onApply && <ListRow label={t("up.mod.apply")} disabled={off} onPress={onApply} />}
        {!present && (waiting
          ? <ListRow label={t("up.userFile.waiting")} caption={t("up.mod.waitingCaption")} spinner detail={t("up.cancel")} onPress={cancelUserFileWatch} />
          : download && <ListRow label={t("up.userFile.download")} chevron disabled={off} onPress={() => void downloadMod(appid, download)} />)}
        <ListRow label={t(present ? "up.userFile.change" : "up.userFile.choose")} chevron disabled={off} onPress={() => void pick()} />
        {present && <ListRow danger label={t("up.userFile.remove")} disabled={off} onPress={() => void run(() => removeUpscalerMod(appid))} />}
      </ListCard>
      {error && <Note tone="warn">{error}</Note>}
    </>
  );
};

export const modDownload = (detail: Pick<GameDetail, "mod_download" | "recipe_info">): string | null =>
  detail.mod_download ?? (detail.recipe_info?.page ? WIKI_PAGE + encodeURI(detail.recipe_info.page) : null);
