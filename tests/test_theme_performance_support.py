import asyncio

from test_tdp_guard_rpc import plugin  # noqa: F401


def test_support_log_records_the_theme_performance_mode(plugin):  # noqa: F811
    assert plugin._support_settings_state()["theme_performance_mode"] is None
    asyncio.run(plugin.set_ui_prefs({"pdc:themePerformanceMode": "1"}))
    assert plugin._support_settings_state()["theme_performance_mode"] == "1"
