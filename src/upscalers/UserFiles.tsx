import { openFilePicker } from "@decky/api";
import { useEffect, useState, type FC } from "react";

import { addUpscalerUserFile, getUpscalerUserFileCandidates, removeUpscalerUserFile } from "../api";
import { useI18n } from "../i18n";
import { upscalerErrorCode } from "./errorCode";
import { holdPage } from "./pageMemory";
import { ListCard, ListRow, Note } from "./parts";
import type { GameDetail, UserFile, UserFileCandidate } from "./types";
import { cancelUserFileWatch, downloadUserFile, onUserFileWatch, watchingFor } from "./userFileWatch";

const EXTENSIONS = ["zip", "7z", "rar", "dll"];

const shortPage = (url: string) => url.replace(/^https:\/\/(www\.)?/, "");

// Steam's browser closes the QAM and unmounts the card: how the download wait ended has to outlive it.
const watchError = new Map<string, string>();
onUserFileWatch((event) => {
  const key = `${event.appid}:${event.dependency}`;
  if (event.type === "failed") watchError.set(key, event.code === "user_file_wrong" ? "up.error.user_file_wrong" : "up.error.user_file_unreadable");
  else if (event.type === "expired") watchError.set(key, "up.error.watch_expired");
  else if (event.type === "watching" || event.type === "adopted") watchError.delete(key);
});

/** Files only the user can download, right under the upscaler: what is missing, which version is in, and where the
 *  file already in Downloads can be picked up with one press. */
export const UserFiles: FC<{
  appid: string;
  files: UserFile[];
  disabled?: boolean;
  onDetail: (detail: GameDetail) => void;
}> = ({ appid, files, disabled = false, onDetail }) => (
  <>
    {files.map((file) => <UserFileCard key={file.id} appid={appid} file={file} disabled={disabled} onDetail={onDetail} />)}
  </>
);

const UserFileCard: FC<{ appid: string; file: UserFile; disabled: boolean; onDetail: (detail: GameDetail) => void }> = ({ appid, file, disabled, onDetail }) => {
  const { t } = useI18n();
  const [folder, setFolder] = useState<string | null>(null);
  const [found, setFound] = useState<UserFileCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(() => {
    const key = watchError.get(`${appid}:${file.id}`);
    return key ? t(key) : null;
  });
  const missing = file.state === "missing";
  const [waiting, setWaiting] = useState(() => watchingFor(appid, file.id));

  useEffect(() => onUserFileWatch((event) => {
    if (event.appid !== appid || event.dependency !== file.id) return;
    setWaiting(event.type === "watching");
    if (event.type === "adopted") onDetail(event.detail);
    const failure = watchError.get(`${appid}:${file.id}`);
    if (failure) setError(t(failure));
  }), [appid, file.id, onDetail, t]);

  useEffect(() => {
    let live = true;
    getUpscalerUserFileCandidates(file.id)
      .then((result) => { if (live) { setFolder(result.folder); setFound(result.candidates); } })
      .catch(() => { if (live) setFound([]); });
    return () => { live = false; };
  }, [file.id, file.state]);

  const run = async (action: () => Promise<GameDetail>) => {
    setBusy(true);
    setError(null);
    try {
      onDetail(await action());
    } catch (failure) {
      const code = upscalerErrorCode(failure);
      setError(t(code === "busy" ? "up.error.busy" : code === "user_file_wrong" ? "up.error.user_file_wrong" : "up.error.user_file_unreadable"));
    } finally {
      setBusy(false);
    }
  };
  const adopt = (path: string) => run(() => addUpscalerUserFile(appid, file.id, path));
  const pick = async () => {
    // The picker opens in Steam's main window and closes the QAM: the game page comes back with the panel.
    holdPage();
    const picked = await openFilePicker(0 as never, folder ?? "/home", true, true, undefined, EXTENSIONS).catch(() => null);
    if (picked?.realpath) await adopt(picked.realpath);
  };

  const status = missing ? t("up.userFile.missing") : file.installed_version ?? file.filename ?? "";
  const caption = missing ? t("up.userFile.where", { page: shortPage(file.page_url), version: file.version })
    : file.state === "avoid" ? t("up.userFile.avoid", { version: file.installed_version ?? "", recommended: file.version })
    : file.state === "other_version" ? t("up.userFile.recommended", { version: file.version })
    : undefined;
  const offered = missing ? found : found.filter((candidate) => candidate.filename !== file.filename).slice(0, 1);

  return (
    <>
      <ListCard>
        <ListRow first label={file.name} detail={status} caption={caption} busy={busy} />
        {offered.map((candidate) => (
          <ListRow key={candidate.path} label={t("up.userFile.use", { name: candidate.filename })}
            caption={candidate.version ?? undefined} disabled={disabled || busy} onPress={() => void adopt(candidate.path)} />
        ))}
        {waiting
          ? <ListRow label={t("up.userFile.waiting")} caption={t("up.userFile.waitingCaption")} spinner detail={t("up.cancel")} onPress={cancelUserFileWatch} />
          : file.state !== "ready" && <ListRow label={t("up.userFile.download")} chevron disabled={disabled || busy} onPress={() => void downloadUserFile(appid, file)} />}
        <ListRow label={t(missing ? "up.userFile.choose" : "up.userFile.change")} chevron disabled={disabled || busy} onPress={() => void pick()} />
        {!missing && (
          <ListRow danger label={t("up.userFile.remove")} disabled={disabled || busy} onPress={() => void run(() => removeUpscalerUserFile(appid, file.id))} />
        )}
      </ListCard>
      {error && <Note tone="warn">{error}</Note>}
    </>
  );
};
