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

/** Vertical game portrait (2:3) with rounded corners + gradient backdrop. Falls back
 *  to a gradient tile with the game's initials when there's no art (or it fails to load). */
export const GameCover: FC<{ url: string | null; name: string; width?: number }> = ({
  url,
  name,
  width = 46,
}) => {
  const [err, setErr] = useState(false);
  // Reset the error on url change — this instance is reused (e.g. the running-now
  // card) as the game changes, so a prior 404 must not stick to the next cover.
  useEffect(() => setErr(false), [url]);
  const height = Math.round(width * 1.5);
  const showImg = !!url && !err;
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
          src={url!}
          onError={() => setErr(true)}
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
