import type { Lang } from "../i18n";

const LANGUAGE_HEADINGS: Record<string, Lang> = {
  Novedades: "es",
  "What's new": "en",
  Novità: "it",
};

const VERSION_HEADING = /^##\s+v\d+\.\d+\.\d+\s*$/m;
const LANGUAGE_HEADING = /^###\s+(.+?)\s*$/;

function localizeRelease(section: string, lang: Lang): string {
  const lines = section.replace(/\r/g, "").trim().split("\n");
  const headings = lines.flatMap((line, index) => {
    const heading = line.match(LANGUAGE_HEADING)?.[1];
    return heading ? [{ index, lang: LANGUAGE_HEADINGS[heading] }] : [];
  });
  const translations = headings.filter(
    (heading): heading is { index: number; lang: Lang } => Boolean(heading.lang),
  );
  if (!translations.length) return lines.join("\n").trim();

  const content = (translation: { index: number }) => {
    const next = headings.find((heading) => heading.index > translation.index);
    return lines.slice(translation.index + 1, next?.index).join("\n").trim();
  };
  const firstNonEmpty = (candidateLang?: Lang) => translations.find(
    (translation) => (!candidateLang || translation.lang === candidateLang)
      && content(translation),
  );
  const selected = firstNonEmpty(lang) ?? firstNonEmpty("en") ?? firstNonEmpty();

  return selected ? [lines[0], content(selected)].join("\n") : lines[0];
}

export function releaseNotesForLanguage(notes: string, lang: Lang): string {
  const starts = [...notes.matchAll(new RegExp(VERSION_HEADING, "gm"))].map(
    (match) => match.index ?? 0,
  );
  if (!starts.length) return notes.trim();

  return starts
    .map((start, index) => notes.slice(start, starts[index + 1]).trim())
    .map((section) => localizeRelease(section, lang))
    .filter(Boolean)
    .join("\n\n");
}
