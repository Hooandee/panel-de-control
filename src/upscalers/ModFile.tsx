import { openFilePicker } from "@decky/api";
import { TextField } from "@decky/ui";
import { useEffect, useState, type FC } from "react";

import { addUpscalerMod, getUpscalerModCandidates, removeUpscalerMod } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { upscalerErrorCode } from "./errorCode";
import { holdPage } from "./pageMemory";
import { ListCard, ListRow, Note } from "./parts";
import type { GameDetail, GameMod } from "./types";
import { cancelUserFileWatch, downloadMod, MOD_WATCH, onUserFileWatch, watchingFor } from "./userFileWatch";

const EXTENSIONS = ["zip", "7z", "rar"];
const PROGRESS_MS = 2000;
// The picker and Steam's browser close the QAM and unmount this card: the last error and a password-protected archive
// have to outlive it, so the download watch's outcome is recorded here even with no card on screen.
const lastError = new Map<string, string>();
const lockedArchive = new Map<string, string>();
const WIKI_PAGE = "https://github.com/optiscaler/OptiScaler/wiki/";

/** The OptiScaler wiki names the mod in its page title: «Elden-Ring-(ERSS‐FG)» → «ERSS-FG». */
export const wikiModName = (page: string | null | undefined): string | null => {
  const named = page?.match(/\(([^()]+)\)$/)?.[1];
  return named ? named.replace(/[‐‑–]/g, "-") : null;
};

const shortName = (name: string) => (name.length > 30 ? `${name.slice(0, 17)}…${name.slice(-12)}` : name);

const needsPassword = (code: string) => code === "mod_password" || code === "mod_password_wrong";

onUserFileWatch((event) => {
  if (event.dependency !== MOD_WATCH) return;
  if (event.type === "expired") {
    lastError.set(event.appid, "watch_expired");
  } else if (event.type === "failed") {
    lastError.set(event.appid, event.code);
    if (needsPassword(event.code) && event.path) lockedArchive.set(event.appid, event.path);
  } else if (event.type === "watching" || event.type === "adopted") {
    lastError.delete(event.appid);
    lockedArchive.delete(event.appid);
  }
});

const errorKey = (code: string) => code === "busy" ? "up.error.busy"
  : code === "watch_expired" ? "up.error.watch_expired"
  : code === "mod_password" ? "up.error.mod_password"
  : code === "mod_password_wrong" ? "up.error.mod_password_wrong"
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
  const [error, setErrorState] = useState<string | null>(() => lastError.get(appid) ?? null);
  const setError = (code: string | null) => {
    if (code) lastError.set(appid, code);
    else lastError.delete(appid);
    setErrorState(code);
  };
  const [waiting, setWaiting] = useState(() => watchingFor(appid, MOD_WATCH));
  const [locked, setLockedState] = useState<string | null>(() => lockedArchive.get(appid) ?? null);
  const setLocked = (path: string | null) => {
    if (path) lockedArchive.set(appid, path);
    else lockedArchive.delete(appid);
    setLockedState(path);
  };
  const [password, setPassword] = useState("");
  const [received, setReceived] = useState<number | null>(null);

  useEffect(() => onUserFileWatch((event) => {
    if (event.appid !== appid || event.dependency !== MOD_WATCH) return;
    setWaiting(event.type === "watching");
    if (event.type === "adopted") onDetail(event.detail);
    setErrorState(lastError.get(appid) ?? null);
    setLockedState(lockedArchive.get(appid) ?? null);
  }), [appid, onDetail]);

  useEffect(() => {
    let live = true;
    getUpscalerModCandidates(appid).then((result) => { if (live) setFolder(result.folder); }).catch(() => undefined);
    return () => { live = false; };
  }, [appid]);

  // Steam's browser shows no download progress: the growing file in Downloads stands in for it.
  useEffect(() => {
    if (!waiting) {
      setReceived(null);
      return undefined;
    }
    let live = true;
    const timer = setInterval(() => {
      getUpscalerModCandidates(appid)
        .then((result) => { if (live) setReceived(result.downloading?.size ?? null); })
        .catch(() => undefined);
    }, PROGRESS_MS);
    return () => { live = false; clearInterval(timer); };
  }, [appid, waiting]);

  const run = async (action: () => Promise<GameDetail>, path?: string) => {
    setBusy(true);
    setError(null);
    try {
      onDetail(await action());
      setLocked(null);
      setPassword("");
    } catch (failure) {
      const code = upscalerErrorCode(failure);
      if (path && needsPassword(code)) setLocked(path);
      setError(code);
    } finally {
      setBusy(false);
    }
  };
  const adopt = (path: string, secret?: string) => run(() => addUpscalerMod(appid, path, secret), path);
  const pick = async () => {
    // A download still being watched would replace the archive picked here once it lands.
    if (watchingFor(appid, MOD_WATCH)) cancelUserFileWatch();
    holdPage();
    const picked = await openFilePicker(0 as never, folder ?? "/home", true, true, undefined, EXTENSIONS).catch(() => null);
    if (picked?.realpath) {
      setLocked(null);
      await adopt(picked.realpath);
    }
  };
  const off = disabled || busy;
  const present = mod && !mod.removed ? mod : null;

  if (!needed && !mod) {
    return (
      <>
        <ListRow label={t("up.mod.add")} chevron disabled={off} busy={busy} onPress={() => void pick()} />
        {error && <Note tone="warn">{t(errorKey(error))}</Note>}
      </>
    );
  }

  const state = mod?.removed ? t("up.mod.state.removing")
    : !present ? t("up.userFile.missing")
    : present.applied ? t("up.mod.state.active")
    : onApply ? t("up.mod.state.pending")
    : t("up.mod.state.ready");
  const caption = present?.filename ? shortName(present.filename) : mod?.removed ? undefined : needed ? t("up.mod.required") : undefined;

  return (
    <>
      <ListCard>
        <ListRow first label={name ? t("up.mod.named", { name }) : t("up.mod.title")}
          detail={state} caption={caption} busy={busy} />
        {mod && !mod.applied && onApply && <ListRow label={t("up.mod.apply")} disabled={off} onPress={onApply} />}
        {!present && (waiting
          ? <ListRow label={t("up.userFile.waiting")} caption={received !== null ? t("up.mod.downloading", { size: (received / 1048576).toFixed(1) }) : t("up.mod.waitingCaption")} spinner detail={t("up.cancel")} onPress={cancelUserFileWatch} />
          : download && <ListRow label={t("up.userFile.download")} chevron disabled={off} onPress={() => void downloadMod(appid, download)} />)}
        {locked && !present && (
          <>
            <div style={{ padding: `${theme.space.xs}px ${theme.space.md}px` }}>
              <TextField label={t("up.mod.password")} bIsPassword value={password} onChange={(event) => setPassword(event.target.value)}
                style={{ background: theme.color.surfaceRaised, color: theme.color.textPrimary, caretColor: theme.color.textPrimary }} />
            </div>
            <ListRow label={t("up.mod.usePassword")} disabled={off || !password} onPress={() => void adopt(locked, password)} />
          </>
        )}
        <ListRow label={t(present ? "up.userFile.change" : "up.userFile.choose")} chevron disabled={off} onPress={() => void pick()} />
        {present && <ListRow danger label={t("up.userFile.remove")} disabled={off} onPress={() => void run(() => removeUpscalerMod(appid))} />}
      </ListCard>
      {error && <Note tone="warn">{t(errorKey(error))}</Note>}
    </>
  );
};

export const modDownload = (detail: Pick<GameDetail, "mod_download" | "recipe_info">): string | null =>
  detail.mod_download ?? (detail.recipe_info?.page ? WIKI_PAGE + encodeURI(detail.recipe_info.page) : null);
