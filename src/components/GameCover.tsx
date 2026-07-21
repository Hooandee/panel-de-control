import { FC, useState, useEffect } from "react";
import { theme } from "../theme";

// Accent-tinted gradient behind the portrait; also the fallback tile when no art.
const GRADIENT = `linear-gradient(155deg, ${theme.color.accent}55, ${theme.color.surface} 88%)`;

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/** Vertical game portrait (2:3) with rounded corners + gradient backdrop. Steam can
 *  return several candidates (e.g. a stale JPG then a valid PNG); we try them in order
 *  and fall back to a gradient tile with the game's initials when none load. */
export const GameCover: FC<{ urls: string[]; name: string; width?: number }> = ({
  urls,
  name,
  width = 46,
}) => {
  const [idx, setIdx] = useState(0);
  // Reset to the first candidate when the list changes — this instance is reused
  // (e.g. the running-now card) as the game changes, so a prior failure can't stick.
  useEffect(() => setIdx(0), [urls.join("|")]);
  const height = Math.round(width * 1.5);
  const url = urls[idx];
  const showImg = !!url;
  return (
    <div
      style={{
        width,
        height,
        flexShrink: 0,
        borderRadius: theme.radius.sm,
        overflow: "hidden",
        background: GRADIENT,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {showImg ? (
        <img
          src={url}
          onError={() => setIdx((i) => i + 1)}
          loading="lazy"
          decoding="async"
          style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
        />
      ) : (
        <span
          style={{
            fontSize: Math.round(width * 0.42),
            fontWeight: 700,
            color: theme.color.textPrimary,
            opacity: 0.85,
            letterSpacing: 0.5,
          }}
        >
          {initials(name)}
        </span>
      )}
    </div>
  );
};
