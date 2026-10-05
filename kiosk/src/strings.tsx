import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DICTS } from "../../src/i18n";
import { PRESET_ICON_KEYS, presetIconNode } from "../../src/tdp/powerPresetIcons";
import { FAN_PRESET_ICON, FanIcon, ICON, LIGHT_MODE_ICON } from "./icons";

const NATIVE_PREFIXES = ["kiosk.", "fans.preset.", "tdp.preset."];

/** The translations the native bottom screen draws, exported to dist/kiosk/strings.json at build time. */
export const STRINGS = Object.fromEntries(
  Object.entries(DICTS).map(([lang, dict]) => [
    lang,
    Object.fromEntries(Object.entries(dict).filter(([key]) => NATIVE_PREFIXES.some((prefix) => key.startsWith(prefix)))),
  ]),
);

const markup = (nodes: Record<string, ReactNode>) =>
  Object.fromEntries(Object.entries(nodes).map(([name, node]) => [name, renderToStaticMarkup(<>{node}</>)]));

/** The same icons as SVG markup, exported to dist/kiosk/icons.json. */
export const ICONS = {
  ...markup(ICON),
  fan: renderToStaticMarkup(createElement(FanIcon)),
  ...Object.fromEntries(Object.entries(markup(LIGHT_MODE_ICON)).map(([k, v]) => [`light.${k}`, v])),
  ...Object.fromEntries(Object.entries(markup(FAN_PRESET_ICON)).map(([k, v]) => [`fan.${k}`, v])),
  ...Object.fromEntries(PRESET_ICON_KEYS.map((name) => [`preset.${name}`, renderToStaticMarkup(<>{presetIconNode(name, 24)}</>)])),
};
