import { describe, expect, it, vi } from "vitest";

import { ThemeImages, themeImageBucket, type ThemeImageEntry, type ThemeImagePicker, type ThemeImageUrls } from "./themeImages";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

const sized = (ref: string, port = 9): ThemeImageUrls => ({
  1280: `http://127.0.0.1:${port}/m/t/sized%3A1280%3A${ref}`,
  1920: `http://127.0.0.1:${port}/m/t/sized%3A1920%3A${ref}`,
  2560: `http://127.0.0.1:${port}/m/t/sized%3A2560%3A${ref}`,
});

const VIDA = "hooandee-vida";

const DUO = "hooandee-duo";

function backend(listed: Record<string, ThemeImageUrls> = {}, owners: Record<string, string[]> = {}) {
  const entries = (): Record<string, ThemeImageEntry> => Object.fromEntries(
    Object.entries(listed).map(([ref, urls]) => [ref, { urls, owners: owners[ref] ?? [VIDA] }]),
  );
  return {
    list: vi.fn(async (): Promise<Record<string, ThemeImageEntry>> => entries()),
    register: vi.fn(async (ref: string, _owner: string, _maxSide: number | null): Promise<{ ref: string; urls: ThemeImageUrls } | { error: string }> =>
      ref === "local:gone" ? { error: "unknown_media" } : { ref, urls: sized(ref) }),
    keep: vi.fn(async (_owner: string, _refs: string[]): Promise<string[]> => []),
  };
}

const choosing = (ref: string): ThemeImagePicker => (request) => request.choose(ref);

describe("themeImageBucket", () => {
  it.each([
    [800, 1280], [1280, 1280], [1281, 1920], [1920, 1920], [2400, 2560], [3840, 2560],
    [undefined, 2560], [0, 2560], [-1, 2560], [Number.NaN, 2560], [Number.POSITIVE_INFINITY, 2560], ["1920", 2560],
  ])("snaps %s up to %s and never above 1440p", (maxSide, bucket) => {
    expect(themeImageBucket(maxSide)).toBe(bucket);
  });
});

describe("ThemeImages", () => {
  it("resolves the explorer's pick with the url for the screen's size, then answers each size synchronously", async () => {
    const images = new ThemeImages(backend(), choosing("local:abc"));
    const changed = vi.fn();
    images.subscribe(changed);
    await expect(images.pick(VIDA, { title: "Fondo", maxSide: 1280 })).resolves.toEqual({ ref: "local:abc", url: sized("local:abc")[1280] });
    expect(images.url(VIDA, "local:abc", 1920)).toBe(sized("local:abc")[1920]);
    expect(images.url(VIDA, "local:abc", 3840)).toBe(sized("local:abc")[2560]);
    expect(images.url(VIDA, "local:abc")).toBe(sized("local:abc")[2560]);
    expect(changed).toHaveBeenCalledOnce();
  });

  it("serves one url for every size when the backend says the original already fits", async () => {
    const original = "http://127.0.0.1:9/m/t/local%3Asmall";
    const server = backend({ "local:small": { 1280: original, 1920: original, 2560: original } });
    const images = new ThemeImages(server, choosing("local:small"));
    await images.refresh();
    expect(new Set([1000, 1600, 2560].map((side) => images.url(VIDA, "local:small", side)))).toEqual(new Set([original]));
  });

  it("answers null for a size the backend could not make", async () => {
    const { 1920: _dropped, ...rest } = sized("local:abc");
    const images = new ThemeImages(backend({ "local:abc": rest }), choosing("local:abc"));
    await images.refresh();
    expect(images.url(VIDA, "local:abc", 1920)).toBeNull();
    expect(images.url(VIDA, "local:abc", 1280)).toBe(rest[1280]);
  });

  it("passes the title to the explorer and settles null when the user backs out", async () => {
    const picker = vi.fn<ThemeImagePicker>(async () => null);
    const images = new ThemeImages(backend(), picker);
    await expect(images.pick(VIDA, { title: "Página 2" })).resolves.toBeNull();
    expect(picker.mock.calls[0][0].title).toBe("Página 2");
  });

  it("opens one explorer at a time", async () => {
    let close!: () => void;
    const picker: ThemeImagePicker = () => new Promise((resolve) => { close = () => resolve(null); });
    const images = new ThemeImages(backend(), picker);
    const first = images.pick(VIDA, {});
    await expect(images.pick(VIDA, {})).resolves.toBeNull();
    close();
    await expect(first).resolves.toBeNull();
    const again = images.pick(VIDA, {});
    close();
    await expect(again).resolves.toBeNull();
  });

  it("never opens for an aborted request and turns a picker failure into null", async () => {
    const controller = new AbortController();
    controller.abort();
    const picker = vi.fn<ThemeImagePicker>(async () => { throw new Error("modal"); });
    const images = new ThemeImages(backend(), picker);
    await expect(images.pick(VIDA, {}, controller.signal)).resolves.toBeNull();
    expect(picker).not.toHaveBeenCalled();
    await expect(images.pick(VIDA, {})).resolves.toBeNull();
  });

  it("refuses a pick the backend cannot serve", async () => {
    const images = new ThemeImages(backend(), choosing("local:gone"));
    await expect(images.pick(VIDA, {})).resolves.toBeNull();
    expect(images.url(VIDA, "local:gone")).toBeNull();
  });

  it("loads remembered refs after a restart and drops a file that disappeared on the next refresh", async () => {
    let now = 0;
    const server = backend({ "local:abc": sized("local:abc", 1) });
    const images = new ThemeImages(server, choosing("local:abc"), () => now);
    const changed = vi.fn();
    images.subscribe(changed);
    expect(images.url(VIDA, "local:abc", 1280)).toBeNull();
    await settle();
    expect(images.url(VIDA, "local:abc", 1280)).toBe(sized("local:abc", 1)[1280]);
    expect(changed).toHaveBeenCalledOnce();
    expect(images.url(VIDA, "local:unknown")).toBeNull();
    expect(server.list).toHaveBeenCalledOnce();
    server.list.mockResolvedValueOnce({} as Record<string, ThemeImageEntry>);
    now = 30_000;
    images.url(VIDA, "local:abc");
    await settle();
    expect(images.url(VIDA, "local:abc")).toBeNull();
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it("retries a failed load sooner and rejects malformed refs without asking the backend", async () => {
    let now = 0;
    const server = backend();
    server.list.mockRejectedValueOnce(new Error("ambient_stopped"));
    const images = new ThemeImages(server, choosing("local:abc"), () => now);
    await images.refresh();
    now = 4_999;
    images.url(VIDA, "local:abc");
    expect(server.list).toHaveBeenCalledOnce();
    now = 5_000;
    images.url(VIDA, "local:abc");
    expect(server.list).toHaveBeenCalledTimes(2);
    expect(images.url(VIDA, "x".repeat(513))).toBeNull();
    expect(images.url(VIDA, 42 as never)).toBeNull();
  });

  it("answers nothing once stopped", async () => {
    const images = new ThemeImages(backend({ "local:abc": sized("local:abc") }), choosing("local:abc"));
    await images.refresh();
    images.stop();
    expect(images.url(VIDA, "local:abc")).toBeNull();
    await expect(images.pick(VIDA, {})).resolves.toBeNull();
  });

  it("registers the pick under the theme with its screen size, so the backend can warm that copy", async () => {
    const server = backend();
    const images = new ThemeImages(server, choosing("local:abc"));
    await images.pick(VIDA, { maxSide: 1600 });
    expect(server.register).toHaveBeenCalledWith("local:abc", VIDA, 1600);
    await images.pick(VIDA, { maxSide: Number.NaN });
    expect(server.register).toHaveBeenLastCalledWith("local:abc", VIDA, null);
    await expect(images.pick("", {})).resolves.toBeNull();
  });

  it("sends a kept set only when it changes, in order, and forgets what the backend dropped", async () => {
    const server = backend({ "local:a": sized("local:a"), "local:b": sized("local:b") });
    const images = new ThemeImages(server, choosing("local:a"));
    await images.refresh();
    const changed = vi.fn();
    images.subscribe(changed);
    images.keep(VIDA, ["local:b", "local:a"]);
    images.keep(VIDA, ["local:a", "local:b", "local:a"]);
    await settle();
    expect(server.keep).toHaveBeenCalledOnce();
    expect(server.keep).toHaveBeenCalledWith(VIDA, ["local:a", "local:b"]);
    server.keep.mockResolvedValueOnce(["local:b"]);
    images.keep(VIDA, ["local:a"]);
    images.keep("hooandee-duo", ["local:a"]);
    await settle();
    expect(server.keep.mock.calls.map((call) => call[0])).toEqual([VIDA, VIDA, "hooandee-duo"]);
    expect(images.url(VIDA, "local:b")).toBeNull();
    expect(images.url(VIDA, "local:a")).not.toBeNull();
    expect(changed).toHaveBeenCalledOnce();
  });

  it("retries a kept set the backend did not take, and ignores invalid input", async () => {
    const server = backend();
    server.keep.mockRejectedValueOnce(new Error("ambient_stopped"));
    const images = new ThemeImages(server, choosing("local:a"));
    images.keep(VIDA, ["local:a"]);
    await settle();
    images.keep(VIDA, ["local:a"]);
    await settle();
    expect(server.keep).toHaveBeenCalledTimes(2);
    for (const bad of [null, "local:a", [3], [""], ["x".repeat(513)], Array(513).fill("local:a")]) images.keep(VIDA, bad);
    images.keep("", ["local:a"]);
    await settle();
    expect(server.keep).toHaveBeenCalledTimes(2);
  });

  it("lets a theme read only the pictures it keeps, plus old ones no theme has claimed", async () => {
    const server = backend({ "local:mine": sized("local:mine"), "local:duo": sized("local:duo"), "local:old": sized("local:old") }, { "local:duo": [DUO], "local:old": [] });
    const images = new ThemeImages(server, choosing("local:duo"));
    await images.refresh();
    expect(images.url(VIDA, "local:mine")).not.toBeNull();
    expect(images.url(VIDA, "local:duo")).toBeNull();
    expect(images.url(DUO, "local:duo")).not.toBeNull();
    expect(images.url(DUO, "local:old")).not.toBeNull();
    await images.pick(VIDA, {});
    expect(images.url(VIDA, "local:duo")).not.toBeNull();
  });

  it("stops answering a picture the theme no longer keeps as soon as the backend took the kept set", async () => {
    const server = backend({ "local:a": sized("local:a"), "local:b": sized("local:b") }, { "local:b": [VIDA, DUO], "local:a": [] });
    const images = new ThemeImages(server, choosing("local:a"));
    await images.refresh();
    images.keep(VIDA, ["local:a"]);
    await settle();
    expect(images.url(VIDA, "local:b")).toBeNull();
    expect(images.url(DUO, "local:b")).not.toBeNull();
    // The unclaimed picture became Vida's by keeping it.
    expect(images.url(DUO, "local:a")).toBeNull();
  });

  it("sends registrations and kept sets in the order themes made them", async () => {
    const server = backend();
    let releaseKeep!: () => void;
    server.keep.mockImplementationOnce(() => new Promise<string[]>((resolve) => { releaseKeep = () => resolve([]); }));
    const images = new ThemeImages(server, choosing("local:new"));
    images.keep(VIDA, ["local:old"]);
    const picked = images.pick(VIDA, {});
    await settle();
    expect(server.register).not.toHaveBeenCalled();
    releaseKeep();
    await expect(picked).resolves.toEqual({ ref: "local:new", url: sized("local:new")[2560] });
    images.keep(VIDA, ["local:new", "local:old"]);
    await settle();
    expect(server.keep.mock.invocationCallOrder[0]).toBeLessThan(server.register.mock.invocationCallOrder[0]);
    expect(server.register.mock.invocationCallOrder[0]).toBeLessThan(server.keep.mock.invocationCallOrder[1]);
  });
});
