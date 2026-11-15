# -*- coding: utf-8 -*-
"""용도별 폴더 정리. 기존 경로명은 directory junction으로 유지."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def move_then_junction(src_name: str, dest: Path):
    """Move ROOT/src_name -> dest, then junction ROOT/src_name -> dest."""
    src = ROOT / src_name
    if not src.exists():
        print("skip missing", src_name)
        return
    # already a junction?
    if src.is_symlink() or (src.exists() and not any(src.iterdir()) and dest.exists()):
        print("skip already?", src_name)
    if dest.exists():
        print("dest exists", dest)
        if src.resolve() == dest.resolve():
            return
        # if src still a real dir and dest exists, abort
        if src.exists() and src.is_dir() and not _is_junction(src):
            print("BOTH exist, skip", src_name, dest)
            return
    ensure_dir(dest.parent)
    if src.exists() and not _is_junction(src):
        print("MOVE", src, "->", dest)
        shutil.move(str(src), str(dest))
    elif not dest.exists():
        print("missing both", src_name)
        return
    # recreate junction at old path
    if src.exists():
        if _is_junction(src):
            print("junction ok", src_name)
            return
        print("old path still exists unexpected", src)
        return
    _mklink_junction(src, dest)
    print("JUNCTION", src, "=>", dest)


def _is_junction(p: Path) -> bool:
    try:
        # reparse point
        import ctypes
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
        return attrs != -1 and bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False


def _mklink_junction(link: Path, target: Path):
    # mklink /J needs cmd
    cmd = f'cmd /c mklink /J "{link}" "{target}"'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(r.stdout or r.stderr)
    if r.returncode != 0:
        raise RuntimeError(f"mklink failed: {r.stderr}")


def move_file(src: Path, dest: Path):
    if not src.exists():
        return
    ensure_dir(dest.parent)
    if dest.exists():
        print("file dest exists", dest)
        return
    shutil.move(str(src), str(dest))
    print("FILE", src.name, "->", dest)


def main():
    ensure_dir(ROOT / "docs" / "experiments")
    ensure_dir(ROOT / "docs" / "archive")
    ensure_dir(ROOT / "docs" / "papers")
    ensure_dir(ROOT / "experiments")
    ensure_dir(ROOT / "data")
    ensure_dir(ROOT / "scripts")

    # experiments
    move_then_junction("run3", ROOT / "experiments" / "run3")
    move_then_junction("pilot", ROOT / "experiments" / "pilot")
    move_then_junction("prep_contract", ROOT / "experiments" / "prep_contract")

    # data
    move_then_junction("standard_forms", ROOT / "data" / "standard_forms")
    move_then_junction("datasets", ROOT / "data" / "datasets")
    move_then_junction("계약 법률 문서 서식 데이터", ROOT / "data" / "aihub_full_package")
    # data_contract stays at root (active pipeline, many refs) — also mirror under data via junction
    dc = ROOT / "data_contract"
    link = ROOT / "data" / "data_contract"
    if dc.exists() and not link.exists():
        _mklink_junction(link, dc)
        print("JUNCTION data/data_contract => data_contract")

    # papers
    papers = ROOT / "관련 논문"
    if papers.exists() and not _is_junction(papers):
        dest = ROOT / "docs" / "papers" / "관련논문"
        if not dest.exists():
            ensure_dir(dest.parent)
            shutil.move(str(papers), str(dest))
            _mklink_junction(papers, dest)
            print("papers moved")

    # root clutter -> docs/archive
    for name in ["AUDIT_RESULTS.csv", "AUDIT_SAMPLES.jsonl", "CURSOR_PROMPT_PILOT.md", "4.45"]:
        move_file(ROOT / name, ROOT / "docs" / "archive" / name)

    # build_catalog into tools
    move_file(ROOT / "build_catalog.py", ROOT / "tools" / "build_catalog.py")

    # organize script itself already under scripts/ if we write there
    print("DONE")


if __name__ == "__main__":
    main()
