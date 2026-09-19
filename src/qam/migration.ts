import { QAM_HOME_TOKEN, type QamLayout } from "./layout";

export function migrateLegacyQamShortcut(layout: QamLayout, enabled: boolean): QamLayout {
  if (!enabled || layout.pinnedViews.includes(QAM_HOME_TOKEN)) return layout;
  return {
    ...layout,
    order: layout.order.includes(QAM_HOME_TOKEN)
      ? layout.order
      : [...layout.order, QAM_HOME_TOKEN],
    pinnedViews: [...layout.pinnedViews, QAM_HOME_TOKEN],
  };
}
