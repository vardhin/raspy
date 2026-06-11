"""Security tests for the Files attachment's path confinement.

The whole attachment's safety rests on Confinement never letting a client-supplied
path escape the configured root — via ``..`` traversal *or* a symlink that points
outside. These tests assert both, including the symlink case which a naive
``Path.resolve`` against the root (without realpath on the candidate) would miss.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from raspy.attachments.files.safety import Confinement


def test_resolves_paths_inside_root(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.txt").write_text("x")
    c = Confinement(tmp_path)

    assert c.resolve("") == tmp_path.resolve()
    assert c.resolve("sub", must_exist=True) == (tmp_path / "sub").resolve()
    assert c.resolve("sub/f.txt", must_exist=True) == (tmp_path / "sub" / "f.txt").resolve()


@pytest.mark.parametrize(
    "bad", ["..", "../..", "../secret", "sub/../../escape", "/../../root", "/../escape"]
)
def test_traversal_escape_is_rejected(tmp_path: Path, bad: str):
    """Paths that resolve *outside* the root raise — even with a leading slash, a
    stripped slash leaves ``..`` parts that still climb out."""
    (tmp_path / "sub").mkdir()
    c = Confinement(tmp_path)
    with pytest.raises(HTTPException):
        c.resolve(bad)


@pytest.mark.parametrize("p", ["/etc/passwd", "....//....//etc", "/home/other"])
def test_absolute_and_odd_paths_stay_inside_root(tmp_path: Path, p: str):
    """Leading slashes / odd dotted names are confined under the root, never above
    it. They needn't raise (they just point at a non-existent in-root path), but
    they must NOT escape — that's the security guarantee."""
    c = Confinement(tmp_path)
    resolved = c.resolve(p)
    assert resolved == c.root or c.root in resolved.parents


def test_symlink_escape_is_rejected(tmp_path: Path):
    # A symlink inside the root pointing at an outside directory must not let the
    # client read through it — realpath on the candidate catches this.
    outside = tmp_path.parent / "outside_target"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret")

    root = tmp_path / "root"
    root.mkdir()
    (root / "escape").symlink_to(outside)
    c = Confinement(root)

    with pytest.raises(HTTPException):
        c.resolve("escape", must_exist=True)
    with pytest.raises(HTTPException):
        c.resolve("escape/secret.txt", must_exist=True)


def test_to_rel_roundtrips(tmp_path: Path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    c = Confinement(tmp_path)
    assert c.to_rel(c.resolve("")) == ""
    assert c.to_rel(c.resolve("a/b")) == "a/b"


def test_nul_byte_rejected(tmp_path: Path):
    c = Confinement(tmp_path)
    with pytest.raises(HTTPException):
        c.resolve("a\x00b")
