# -*- coding: utf-8 -*-
"""B/C train·eval loss 그래프 PNG 생성."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUN3 = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3")
OUT = RUN3 / "FOR_CLAUDE"


def load_hist(side: str):
    base = RUN3 / f"adapter_{side}" / "checkpoints"
    cands = sorted(base.glob("checkpoint-*/trainer_state.json"), key=lambda p: p.stat().st_mtime)
    st = json.loads(cands[-1].read_text(encoding="utf-8"))
    steps, losses = [], []
    eval_steps, eval_losses = [], []
    for h in st.get("log_history", []):
        if "loss" in h:
            steps.append(h["step"])
            losses.append(h["loss"])
        if "eval_loss" in h:
            eval_steps.append(h["step"])
            eval_losses.append(h["eval_loss"])
    return steps, losses, eval_steps, eval_losses, st


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), dpi=150)
    for ax, side, color in [(axes[0], "B", "#1f77b4"), (axes[1], "C", "#d62728")]:
        steps, losses, es, el, st = load_hist(side)
        ax.plot(steps, losses, "o-", color=color, label="train loss", markersize=4)
        if es:
            ax.plot(es, el, "s--", color="black", label="eval loss", markersize=5)
        ax.set_title(
            f"Model {side}  (epochs={st.get('num_train_epochs')}, max_steps={st.get('max_steps')})"
        )
        ax.set_xlabel("step")
        ax.set_ylabel("loss")
        ax.grid(True, alpha=0.3)
        ax.legend()
    fig.suptitle("QLoRA train/eval loss (trainer_state.json)", fontsize=12)
    fig.tight_layout()
    p_all = OUT / "loss_BC.png"
    fig.savefig(p_all, bbox_inches="tight")
    plt.close(fig)

    for side, color in [("B", "#1f77b4"), ("C", "#d62728")]:
        steps, losses, es, el, st = load_hist(side)
        fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
        ax.plot(steps, losses, "o-", color=color, label="train loss", markersize=4)
        if es:
            ax.plot(es, el, "s--", color="black", label="eval loss", markersize=5)
        ax.set_title(f"Model {side} loss")
        ax.set_xlabel("step")
        ax.set_ylabel("loss")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        p = OUT / f"loss_{side}.png"
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        print(f"{side}: train_n={len(steps)} eval_n={len(es)} -> {p}")

    for p in [OUT / "loss_BC.png", OUT / "loss_B.png", OUT / "loss_C.png"]:
        print(f"{p.name}\t{p.stat().st_size}\tbytes")


if __name__ == "__main__":
    main()
