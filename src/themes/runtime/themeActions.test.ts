import { describe, expect, it, vi } from "vitest";

import { ThemeActionsChannel } from "./themeActions";

describe("theme actions channel", () => {
  it("delivers an action to every listener of that theme and to no other theme", () => {
    const channel = new ThemeActionsChannel();
    const first = vi.fn();
    const second = vi.fn();
    const other = vi.fn();
    channel.subscribe("hooandee-vida", first);
    channel.subscribe("hooandee-vida", second);
    channel.subscribe("hooandee-duo", other);

    expect(channel.dispatch("hooandee-vida", "reset-home")).toBe(2);
    expect(first).toHaveBeenCalledWith("reset-home");
    expect(second).toHaveBeenCalledWith("reset-home");
    expect(other).not.toHaveBeenCalled();
  });

  it("tells watchers when a theme starts and stops listening, and forgets empty themes", () => {
    const channel = new ThemeActionsChannel();
    const watcher = vi.fn();
    const stopWatching = channel.watch(watcher);
    expect(channel.listening("hooandee-vida")).toBe(false);

    const off = channel.subscribe("hooandee-vida", () => {});
    expect(channel.listening("hooandee-vida")).toBe(true);
    off();
    off();
    expect(channel.listening("hooandee-vida")).toBe(false);
    expect(watcher).toHaveBeenCalledTimes(2);

    stopWatching();
    channel.subscribe("hooandee-vida", () => {});
    expect(watcher).toHaveBeenCalledTimes(2);
  });

  it("isolates a listener that throws and does not count it as delivered", () => {
    const log = vi.fn();
    const channel = new ThemeActionsChannel(log);
    const healthy = vi.fn();
    channel.subscribe("hooandee-vida", () => { throw new Error("boom"); });
    channel.subscribe("hooandee-vida", healthy);

    expect(channel.dispatch("hooandee-vida", "reset-home")).toBe(1);
    expect(healthy).toHaveBeenCalledOnce();
    expect(log).toHaveBeenCalledWith("action_listener_failed");
  });

  it("ignores a listener that is not a function", () => {
    const channel = new ThemeActionsChannel();
    channel.subscribe("hooandee-vida", "nope" as never)();
    expect(channel.listening("hooandee-vida")).toBe(false);
  });
});
