import { openFilePicker } from "@decky/api";
import { useEffect, useState, type FC } from "react";

import { addUpscalerUserFile, getUpscalerUserFileCandidates, removeUpscalerUserFile } from "../api";
import { useI18n } from "../i18n";
import { upscalerErrorCode } from "./errorCode";
import { ListCard, ListRow, Note } from "./parts";
import type { GameDetail, UserFile, UserFileCandidate } from "./types";

const EXTENSIONS = ["zip", "7z", "rar", "dll"];

const shortPage = (url: string) => url.replace(/^https:\/\/(www\.)?/, "");

/** Files only the user can download, right under the upscaler: what is missing, which version is in, and where the
 *  file the user already saved in desktop mode can be picked up with one press. */
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
  const [error, setError] = useState<string | null>(null);
  const missing = file.state === "missing";

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
      setError(t(code === "user_file_wrong" ? "up.error.user_file_wrong" : "up.error.user_file_unreadable"));
    } finally {
      setBusy(false);
    }
  };
  const adopt = (path: string) => run(() => addUpscalerUserFile(appid, file.id, path));
  const pick = async () => {
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
        <ListRow label={t(missing ? "up.userFile.choose" : "up.userFile.change")} chevron disabled={disabled || busy} onPress={() => void pick()} />
        {!missing && (
          <ListRow danger label={t("up.userFile.remove")} disabled={disabled || busy} onPress={() => void run(() => removeUpscalerUserFile(appid, file.id))} />
        )}
      </ListCard>
      {error && <Note tone="warn">{error}</Note>}
    </>
  );
};
