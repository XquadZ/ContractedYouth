# -*- coding: utf-8 -*-
"""Load LAW_OC/HF_TOKEN from Windows User env, then exec target script."""
from __future__ import annotations

import os
import runpy
import sys


def user_env(name: str) -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
            try:
                val, _ = winreg.QueryValueEx(k, name)
                return str(val or "")
            except FileNotFoundError:
                return ""
    except Exception:
        return ""


def main():
    if len(sys.argv) < 2:
        print("usage: _run_with_user_env.py script.py")
        sys.exit(2)
    script = sys.argv[1]
    oc = os.environ.get("LAW_OC") or user_env("LAW_OC")
    hf = os.environ.get("HF_TOKEN") or user_env("HF_TOKEN")
    if oc:
        os.environ["LAW_OC"] = oc.strip()
    if hf:
        os.environ["HF_TOKEN"] = hf.strip()
        os.environ["HUGGING_FACE_HUB_TOKEN"] = hf.strip()
    print("LAW_OC_set", bool(os.environ.get("LAW_OC", "").strip()), "HF_set", bool(os.environ.get("HF_TOKEN", "").strip()))
    sys.argv = [script] + sys.argv[2:]
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
