// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { FilesTab } from "./FilesTab";

vi.mock("@decky/api", () => ({ openFilePicker: vi.fn() }));
vi.mock("@decky/ui", async () => {
  const { forwardRef } = await import("react");
  const flows = new Set(["column", "column-reverse", "row", "row-reverse", "grid", "geometric"]);
  return { Focusable: forwardRef(({ children, onClick, onSecondaryButton, onSecondaryActionDescription, onCancelButton, "data-library-column": column, "flow-children": flow }: any, ref: any) => {
    if (flow !== undefined && !flows.has(flow)) throw new Error(`Unhandled flow-children: ${flow}`);
    return <div ref={ref} onClick={onClick} data-library-column={column} data-navigation-flow={flow} data-secondary-action={onSecondaryActionDescription} onKeyDown={(event) => {
      if (event.key === "Escape") onCancelButton?.({ preventDefault: () => event.preventDefault(), stopPropagation: () => event.stopPropagation() });
      if (event.key === "x") onSecondaryButton?.({ detail: { is_repeat: event.repeat }, preventDefault: () => event.preventDefault(), stopPropagation: () => event.stopPropagation() });
    }}>{children}</div>;
  }) };
});
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string, vars?: { n?: number }) => vars?.n === undefined ? key : `${key}:${vars.n}` }) }));
vi.mock("./NowPlaying", () => ({
  RoundButton: ({ label, onActivate }: any) => <button onClick={onActivate}>{label}</button>,
  NowPlaying: ({ player }: any) => <div data-testid="mini-player">{player.track.title}</div>,
}));
vi.mock("./primitives", () => ({
  Button: ({ label, onActivate, disabled }: any) => <button disabled={disabled} onClick={onActivate}>{label}</button>,
  Caption: ({ children }: any) => <div>{children}</div>,
  Row: ({ title, onActivate, trailing }: any) => <div><button onClick={onActivate}>{title}</button>{trailing}</div>,
  menuHandlers: () => ({}),
}));
vi.mock("./stationsParts", () => ({
  Empty: ({ text }: any) => <div>{text}</div>,
  ROW_HEIGHT: 56,
  useMeasuredHeight: () => [() => undefined, 280],
}));

afterEach(cleanup);

function fixture() {
  const runtime = {
    beginLibrarySession: vi.fn(() => vi.fn()),
    previewLibraryMedia: vi.fn().mockResolvedValue(undefined),
    saveLibrarySelection: vi.fn().mockResolvedValue(undefined),
    previewMedia: vi.fn().mockResolvedValue("http://localhost/photo"),
    useBackground: vi.fn().mockResolvedValue(undefined),
    useBackgroundSelection: vi.fn().mockResolvedValue(undefined),
    playMedia: vi.fn().mockResolvedValue(undefined),
    playCollection: vi.fn().mockResolvedValue(true),
    enqueueItems: vi.fn().mockResolvedValue(2),
    removeItem: vi.fn().mockResolvedValue(true),
  } as unknown as AmbientRuntime;
  const snapshot = {
    state: { collections: [{ id: "folder.shared", kind: "folder", name: "Shared", path: "/shared" }], knownFolders: { images: [], videos: [], music: [] }, settings: { background: { pinned: "" } } },
    scan: { library: { "folder.shared": [
      { id: "local:photo", kind: "image", name: "Photo.jpg" },
      { id: "local:video", kind: "video", name: "Film.mp4" },
      { id: "local:song", kind: "audio", name: "Song.mp3" },
    ] }, collections: {}, music: [] },
  } as unknown as AmbientSnapshot;
  return { runtime, snapshot, onClose: vi.fn() };
}

it("chooses an individual image from a shared folder without asking for collection selection", async () => {
  const props = fixture();
  render(<FilesTab {...props} purpose="background" header={null} />);
  fireEvent.click(await screen.findByText("Photo.jpg"));
  expect(screen.queryByText("Song.mp3")).toBeNull();
  await waitFor(() => expect(props.runtime.previewMedia).toHaveBeenCalledWith("local:photo"));
  const preview = screen.getByRole("complementary", { name: "Photo.jpg" });
  expect(preview.contains(await screen.findByRole("img", { name: "Photo.jpg" }))).toBe(true);
  expect(preview.contains(screen.getByText("ambient.lib.save"))).toBe(false);
  fireEvent.click(screen.getByText("ambient.lib.save"));
  await waitFor(() => expect(props.runtime.saveLibrarySelection).toHaveBeenCalledWith([{ ref: "local:photo", kind: "image", name: "Photo.jpg", collection: "folder.shared" }], "background"));
});

it("offers video and audio from the same folder for playback", async () => {
  const props = fixture();
  render(<FilesTab {...props} purpose="playback" header={null} />);
  fireEvent.click(await screen.findByText("Film.mp4"));
  expect(screen.queryByText("Photo.jpg")).toBeNull();
  expect(screen.getByText("Song.mp3")).toBeTruthy();
  fireEvent.click(screen.getByText("ambient.lib.save"));
  await waitFor(() => expect(props.runtime.saveLibrarySelection).toHaveBeenCalledWith([{ ref: "local:video", kind: "video", name: "Film.mp4", collection: "folder.shared" }], "playback"));
  expect(props.onClose).toHaveBeenCalledOnce();
});

it("removes a folder through the shared library scope", async () => {
  const props = fixture();
  render(<FilesTab {...props} purpose="playback" header={null} />);
  fireEvent.click(screen.getByText("ambient.lib.remove"));
  await waitFor(() => expect(props.runtime.removeItem).toHaveBeenCalledWith("library", "folder.shared"));
});

it("places the music player in the preview pane, including while browsing another song", async () => {
  const props = fixture();
  props.snapshot.player = { track: { id: "local:playing", title: "Current song" }, status: "playing" } as AmbientSnapshot["player"];
  render(<FilesTab {...props} purpose="playback" header={<h1>Library</h1>} />);
  expect(screen.getByRole("complementary").contains(document.querySelector("[data-library-player-dock]"))).toBe(true);
  fireEvent.click(await screen.findByText("Song.mp3"));
  expect(screen.getByRole("complementary", { name: "Song.mp3" }).contains(document.querySelector("[data-library-player-dock]"))).toBe(true);
  expect(props.snapshot.player.track?.title).toBe("Current song");
  expect(props.runtime.previewLibraryMedia).not.toHaveBeenCalled();
});

it("keeps legacy music reachable when the backend has no shared library inventory", async () => {
  const props = fixture();
  props.snapshot.scan = { collections: {}, music: [{ id: "local:legacy", kind: "audio", name: "Legacy.mp3", size: 1, mtime: 1 }], truncated: false };
  props.snapshot.state!.collections = [];
  render(<FilesTab {...props} purpose="playback" header={null} />);
  expect(await screen.findByText("Legacy.mp3")).toBeTruthy();
});

function twoSources() {
  const props = fixture();
  props.snapshot.state!.collections.push({ id: "folder.other", kind: "folder", name: "Other", path: "/other" });
  props.snapshot.scan!.library!["folder.other"] = [
    { id: "local:other", kind: "image", name: "Other.jpg", size: 1, mtime: 1 },
    { id: "local:other-song", kind: "audio", name: "Other.mp3", size: 1, mtime: 1 },
    { id: "local:other-next", kind: "audio", name: "Other next.mp3", size: 1, mtime: 1 },
  ];
  return props;
}

it("opens the pinned background source instead of the first folder", async () => {
  const props = twoSources();
  props.snapshot.state!.settings.background.pinned = "local:other";
  render(<FilesTab {...props} purpose="background" header={null} />);
  expect(await screen.findByText("Other.jpg")).toBeTruthy();
  expect(screen.queryByText("Photo.jpg")).toBeNull();
});

it("opens the current track folder and keeps a manually chosen source when the track changes", async () => {
  const props = twoSources();
  props.snapshot.player = { track: { id: "local:other-song" } } as AmbientSnapshot["player"];
  const view = render(<FilesTab {...props} purpose="playback" header={null} />);
  expect(await screen.findByText("Other.mp3")).toBeTruthy();
  fireEvent.click(screen.getByText("Shared"));
  expect(await screen.findByText("Song.mp3")).toBeTruthy();
  const snapshot = { ...props.snapshot, player: { ...props.snapshot.player, track: { ...props.snapshot.player.track!, id: "local:other-next" }, position: 30 } };
  view.rerender(<FilesTab runtime={props.runtime} snapshot={snapshot} purpose="playback" header={null} />);
  expect(screen.getByText("Song.mp3")).toBeTruthy();
  expect(screen.queryByText("Other.mp3")).toBeNull();
});

it("plays several chosen songs, queues them, or plays the whole folder", async () => {
  const props = twoSources();
  render(<FilesTab {...props} purpose="playback" header={null} />);
  fireEvent.click(await screen.findByText("Other"));
  await screen.findByText("Other.mp3");
  fireEvent.click(screen.getByText("ambient.lib.playFolder"));
  await waitFor(() => expect(props.runtime.playCollection).toHaveBeenCalledWith("folder.other", "now"));
  fireEvent.click(screen.getByText("ambient.lib.chooseSeveral"));
  expect(screen.queryByText("Other.jpg")).toBeNull();
  fireEvent.click(screen.getByText("Other next.mp3"));
  fireEvent.click(screen.getByText("Other.mp3"));
  fireEvent.click(screen.getByText("ambient.queue.addEnd"));
  await waitFor(() => expect(props.runtime.enqueueItems).toHaveBeenCalledWith([
    expect.objectContaining({ ref: "local:other-next" }), expect.objectContaining({ ref: "local:other-song" }),
  ], "end"));
});

it("preserves checked photos across folders and rotates only the chosen images", async () => {
  const props = twoSources();
  render(<FilesTab {...props} purpose="background" header={null} />);
  await screen.findByText("Photo.jpg");
  fireEvent.click(screen.getByText("ambient.lib.chooseSeveral"));
  expect(screen.queryByText("Film.mp4")).toBeNull();
  fireEvent.click(screen.getByText("Photo.jpg"));
  expect(screen.getByRole("checkbox", { name: "Photo.jpg" }).getAttribute("aria-checked")).toBe("true");
  fireEvent.click(screen.getByText("Other"));
  fireEvent.click(await screen.findByText("Other.jpg"));
  fireEvent.click(screen.getByText("Shared"));
  await screen.findByText("Photo.jpg");
  expect(screen.getByRole("checkbox", { name: "Photo.jpg" }).getAttribute("aria-checked")).toBe("true");
  fireEvent.click(screen.getByText("ambient.lib.save"));
  await waitFor(() => expect(props.runtime.saveLibrarySelection).toHaveBeenCalledWith([
    { ref: "local:photo", kind: "image", name: "Photo.jpg", collection: "folder.shared" },
    { ref: "local:other", kind: "image", name: "Other.jpg", collection: "folder.other" },
  ], "background"));
});

it("rehydrates existing photo selection and cancel returns to single selection", async () => {
  const props = twoSources();
  props.snapshot.state!.settings.background.selectedRefs = ["local:photo", "local:other"];
  render(<FilesTab {...props} purpose="background" header={null} />);
  await screen.findByText("Photo.jpg");
  fireEvent.click(screen.getByText("ambient.lib.chooseSeveral"));
  expect(screen.getByRole("checkbox", { name: "Photo.jpg" }).getAttribute("aria-checked")).toBe("true");
  expect(screen.getByText("ambient.lib.save")).toBeTruthy();
  fireEvent.click(screen.getByText("ambient.lib.cancelSelection"));
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(screen.getByText("Film.mp4")).toBeTruthy();
  fireEvent.click(screen.getByText("Photo.jpg"));
  expect(screen.getByText("ambient.lib.save")).toBeTruthy();
  expect(props.runtime.useBackgroundSelection).not.toHaveBeenCalled();
});


it("previews the focused song with X and saves that same item without a duplicate playback action", async () => {
  const props = fixture();
  render(<FilesTab {...props} purpose="playback" header={null} />);
  fireEvent.click(await screen.findByText("Film.mp4"));
  fireEvent.keyDown(screen.getByText("Song.mp3"), { key: "x" });
  await waitFor(() => expect(props.runtime.previewLibraryMedia).toHaveBeenCalledExactlyOnceWith({ ref: "local:song", kind: "audio", name: "Song.mp3", collection: "folder.shared" }));
  expect(screen.getByRole("complementary", { name: "Song.mp3" })).toBeTruthy();
  expect(screen.getByText("Song.mp3").closest("[data-secondary-action]")?.getAttribute("data-secondary-action")).toBe("ambient.lib.preview");
  const save = screen.getByText("ambient.lib.save");
  expect(save.closest("[data-library-column]")?.getAttribute("data-library-column")).toBe("2");
  expect(props.runtime.saveLibrarySelection).not.toHaveBeenCalled();
  fireEvent.click(save);
  await waitFor(() => expect(props.runtime.saveLibrarySelection).toHaveBeenCalledWith([{ ref: "local:song", kind: "audio", name: "Song.mp3", collection: "folder.shared" }], "playback"));
  expect(props.onClose).toHaveBeenCalledOnce();
});

it("omits X for photos and never changes checked photos through X", async () => {
  const props = twoSources();
  render(<FilesTab {...props} purpose="background" header={null} />);
  await screen.findByText("Photo.jpg");
  fireEvent.click(screen.getByText("ambient.lib.chooseSeveral"));
  fireEvent.keyDown(screen.getByText("Photo.jpg"), { key: "x" });
  expect(screen.queryByRole("img", { name: "Photo.jpg" })).toBeNull();
  expect(screen.getByRole("checkbox", { name: "Photo.jpg" }).getAttribute("aria-checked")).toBe("false");
  expect(screen.getByText("Photo.jpg").closest("[data-secondary-action]")).toBeNull();
  expect(props.runtime.previewLibraryMedia).not.toHaveBeenCalled();
  expect(props.runtime.saveLibrarySelection).not.toHaveBeenCalled();
});

it("never mounts a second video player: A selects and X delegates to the shared player", async () => {
  const props = fixture();
  const view = render(<FilesTab {...props} purpose="background" header={null} />);
  fireEvent.click(await screen.findByText("Film.mp4"));
  expect(view.container.querySelector("video,audio,iframe")).toBeNull();
  expect(props.runtime.previewLibraryMedia).not.toHaveBeenCalled();
  expect(props.runtime.previewMedia).not.toHaveBeenCalled();
  fireEvent.keyDown(screen.getByText("Film.mp4"), { key: "x" });
  await waitFor(() => expect(props.runtime.previewLibraryMedia).toHaveBeenCalledWith({ ref: "local:video", kind: "video", name: "Film.mp4", collection: "folder.shared" }));
  expect(view.container.querySelector("video,audio,iframe")).toBeNull();
  expect(props.runtime.saveLibrarySelection).not.toHaveBeenCalled();
});

it("ignores held X and duplicate pending preview, and reports failures", async () => {
  const props = fixture();
  let reject!: (error: Error) => void;
  vi.mocked(props.runtime.previewLibraryMedia).mockReturnValue(new Promise((_, fail) => { reject = fail; }));
  render(<FilesTab {...props} purpose="playback" header={null} />);
  const song = await screen.findByText("Song.mp3");
  fireEvent.keyDown(song, { key: "x", repeat: true });
  expect(props.runtime.previewLibraryMedia).not.toHaveBeenCalled();
  fireEvent.keyDown(song, { key: "x" });
  fireEvent.keyDown(song, { key: "x" });
  expect(props.runtime.previewLibraryMedia).toHaveBeenCalledOnce();
  reject(new Error("unavailable"));
  await screen.findByText("ambient.lib.actionFailed");
});

it("ends the preview session when leaving and does not close on failed save", async () => {
  const props = fixture();
  vi.mocked(props.runtime.saveLibrarySelection).mockRejectedValue(new Error("disk full"));
  const view = render(<FilesTab {...props} purpose="playback" header={null} />);
  fireEvent.click(await screen.findByText("Song.mp3"));
  fireEvent.click(screen.getByText("ambient.lib.save"));
  await screen.findByText("ambient.lib.actionFailed");
  expect(props.onClose).not.toHaveBeenCalled();
  expect(props.runtime.beginLibrarySession).toHaveBeenCalledOnce();
  const endSession = vi.mocked(props.runtime.beginLibrarySession).mock.results[0].value;
  view.unmount();
  expect(endSession).toHaveBeenCalledOnce();
});

it("replaces the photo selection when explicitly previewing a video so Save applies what is shown", async () => {
  const props = fixture();
  props.snapshot.player = { track: { id: "local:video", title: "Film" }, status: "playing", video: true } as AmbientSnapshot["player"];
  render(<FilesTab {...props} purpose="background" header={null} />);
  fireEvent.click(await screen.findByText("Photo.jpg"));
  expect(await screen.findByRole("img", { name: "Photo.jpg" })).toBeTruthy();
  fireEvent.keyDown(screen.getByText("Film.mp4"), { key: "x" });
  await waitFor(() => expect(screen.queryByRole("img")).toBeNull());
  expect(document.querySelector("[data-library-player-dock]")).toBeTruthy();
  fireEvent.click(screen.getByText("ambient.lib.save"));
  await waitFor(() => expect(props.runtime.saveLibrarySelection).toHaveBeenCalledWith([{ ref: "local:video", kind: "video", name: "Film.mp4", collection: "folder.shared" }], "background"));
});

it("B exits fullscreen before navigating or cancelling the library", () => {
  const props = fixture();
  const state = { videoFullscreen: true };
  props.runtime.getSnapshot = () => state as AmbientSnapshot;
  props.runtime.setVideoFullscreen = vi.fn((on) => { state.videoFullscreen = on; });
  const view = render(<FilesTab {...props} purpose="playback" header={null} />);
  fireEvent.keyDown(view.container.firstElementChild!, { key: "Escape" });
  expect(props.runtime.setVideoFullscreen).toHaveBeenCalledWith(false);
  expect(props.onClose).not.toHaveBeenCalled();
  fireEvent.keyDown(view.container.firstElementChild!, { key: "Escape" });
  expect(props.onClose).toHaveBeenCalledOnce();
});
