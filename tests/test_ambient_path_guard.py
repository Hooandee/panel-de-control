import os

from ambient.core.media_types import media_kind, mime_type
from ambient.core.path_guard import resolve_servable


def test_file_inside_root_is_servable(tmp_path):
    root = tmp_path / "Pictures"
    root.mkdir()
    photo = root / "a.jpg"
    photo.write_bytes(b"x")
    assert resolve_servable(str(photo), [str(root)]) == os.path.realpath(photo)


def test_nested_file_is_servable(tmp_path):
    (tmp_path / "Pictures" / "trip").mkdir(parents=True)
    photo = tmp_path / "Pictures" / "trip" / "b.png"
    photo.write_bytes(b"x")
    assert resolve_servable(str(photo), [str(tmp_path / "Pictures")]) is not None


def test_parent_traversal_is_rejected(tmp_path):
    root = tmp_path / "Pictures"
    root.mkdir()
    secret = tmp_path / "secret.jpg"
    secret.write_bytes(b"x")
    assert resolve_servable(str(root / ".." / "secret.jpg"), [str(root)]) is None


def test_symlink_escaping_root_is_rejected(tmp_path):
    root = tmp_path / "Pictures"
    root.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"x")
    (root / "link.jpg").symlink_to(outside)
    assert resolve_servable(str(root / "link.jpg"), [str(root)]) is None


def test_sibling_prefix_directory_is_rejected(tmp_path):
    root = tmp_path / "Pictures"
    root.mkdir()
    evil = tmp_path / "Pictures-evil"
    evil.mkdir()
    (evil / "c.jpg").write_bytes(b"x")
    assert resolve_servable(str(evil / "c.jpg"), [str(root)]) is None


def test_directory_and_missing_are_rejected(tmp_path):
    assert resolve_servable(str(tmp_path), [str(tmp_path)]) is None
    assert resolve_servable(str(tmp_path / "nope.jpg"), [str(tmp_path)]) is None


def test_unsupported_extension_is_rejected(tmp_path):
    script = tmp_path / "run.sh"
    script.write_bytes(b"x")
    assert resolve_servable(str(script), [str(tmp_path)]) is None


def test_media_kinds():
    assert media_kind("a.JPG") == "image"
    assert media_kind("clip.webm") == "video"
    assert media_kind("song.opus") == "audio"
    assert media_kind("doc.pdf") is None
    assert mime_type("x.mp4") == "video/mp4"
    assert mime_type("x.avif") == "image/avif"
