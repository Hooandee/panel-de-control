import { openFilePicker } from "@decky/api";
import { useEffect, useState, type FC } from "react";

import { addUpscalerMod, getUpscalerModCandidates, removeUpscalerMod } from "../api";
import { useI18n } from "../i18n";
import { upscalerErrorCode } from "./errorCode";
import { ListCard, ListRow, Note } from "./parts";
import type { GameDetail, GameMod, UserFileCandidate } from "./types";

const EXTENSIONS = ["zip", "7z", "rar"];

/** The OptiScaler wiki names the mod in its page title: «Elden-Ring-(ERSS‐FG)» → «ERSS-FG». */
export const wikiModName = (page: string | null | undefined): string | null => {
  const named = page?.match(/\(([^()]+)\)$/)?.[1];
  return named ? named.replace(/[‐‑–]/g, "-") : null;
};

/** A mod the user brings for this game: Panel copies its files beside the exe with OptiScaler and takes them out with
 *  it. Games the wiki says need one get the full card; any other game gets a single row to add one. */
export const ModFile: FC<{
  appid: string;
  mod: GameMod | null;
  needed: boolean;
  name: string | null;
  disabled?: boolean;
  onDetail: (detail: GameDetail) => void;
}> = ({ appid, mod, needed, name, disabled = false, onDetail }) => {
  const { t } = useI18n();
  const [folder, setFolder] = useState<string | null>(null);
  const [found, setFound] = useState<UserFileCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const full = needed || !!mod;

  useEffect(() => {
    if (!full) return;
    let live = true;
    getUpscalerModCandidates(appid)
      .then((result) => { if (live) { setFolder(result.folder); setFound(result.candidates); } })
      .catch(() => { if (live) setFound([]); });
    return () => { live = false; };
  }, [appid, full, mod?.filename]);

  const run = async (action: () => Promise<GameDetail>) => {
    setBusy(true);
    setError(null);
    try {
      onDetail(await action());
    } catch (failure) {
      const code = upscalerErrorCode(failure);
      setError(t(code === "busy" ? "up.error.busy"
        : code === "mod_unsafe_archive" || code === "mod_too_large" || code === "mod_too_many_files" ? "up.error.mod_unsafe"
        : "up.error.mod_unreadable"));
    } finally {
      setBusy(false);
    }
  };
  const adopt = (path: string) => run(() => addUpscalerMod(appid, path));
  const pick = async () => {
    const picked = await openFilePicker(0 as never, folder ?? "/home", true, true, undefined, EXTENSIONS).catch(() => null);
    if (picked?.realpath) await adopt(picked.realpath);
  };

  if (!full) {
    return <ListRow label={t("up.mod.add")} chevron disabled={disabled || busy} busy={busy} onPress={() => void pick()} />;
  }

  const caption = !mod ? t("up.mod.where")
    : !mod.applied ? t("up.mod.pending")
    : t("up.mod.files", { count: mod.count });
  const offered = (mod ? found.filter((candidate) => candidate.filename !== mod.filename) : found).slice(0, mod ? 1 : 3);

  return (
    <>
      <ListCard>
        <ListRow first label={name ? t("up.mod.named", { name }) : t("up.mod.title")}
          detail={mod?.filename ?? t("up.userFile.missing")} caption={caption} busy={busy} />
        {offered.map((candidate) => (
          <ListRow key={candidate.path} label={t("up.userFile.use", { name: candidate.filename })}
            disabled={disabled || busy} onPress={() => void adopt(candidate.path)} />
        ))}
        <ListRow label={t(mod ? "up.userFile.change" : "up.userFile.choose")} chevron disabled={disabled || busy} onPress={() => void pick()} />
        {mod && <ListRow danger label={t("up.userFile.remove")} disabled={disabled || busy} onPress={() => void run(() => removeUpscalerMod(appid))} />}
      </ListCard>
      <Note>{t("up.mod.safety")}</Note>
      {error && <Note tone="warn">{error}</Note>}
    </>
  );
};
