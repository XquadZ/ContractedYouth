(() => {
  let dialog, frame, pending = null;
  const origin = () => new URL(document.baseURI).origin;

  function ensure() {
    if (dialog) return;
    dialog = document.createElement("dialog");
    dialog.style.cssText =
      "position:fixed;inset:0;width:100%;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;border:0;background:#f5f7fb";
    dialog.setAttribute("aria-label", "원본 계약서와 검토 리포트");
    frame = document.createElement("iframe");
    frame.title = "계약서 검토 워크스페이스";
    frame.style.cssText = "display:block;width:100%;height:100%;border:0";
    dialog.append(frame);
    document.body.append(dialog);
  }

  function deliver() {
    if (!frame?.contentWindow || !pending) return;
    frame.contentWindow.postMessage(pending, origin());
    pending = null;
  }

  window.contractReview = {
    /**
     * open() — 샘플 리포트 먼저 보기
     * open(File) — PDF 워크스페이스
     * open({ ax:true, sampleId, title }) — 같은 화면 + A.X 분석
     */
    open(arg) {
      ensure();
      if (arg instanceof File) {
        pending = { type: "contract-review-file", file: arg };
      } else if (arg && arg.ax) {
        pending = {
          type: "contract-review-ax",
          sampleId: arg.sampleId,
          title: arg.title || "A.X 샘플 분석",
          domainLabel: arg.domainLabel || "",
        };
      } else {
        pending = { type: "contract-review-open" };
      }
      const base = new URL("/static/review.html", document.baseURI);
      if (arg && arg.ax) base.searchParams.set("ax", "1");
      if (arg && arg.sampleVisual) base.searchParams.set("sample", arg.sampleVisual);
      // 파일 업로드가 아닌 샘플 진입은 로그인 없이 허용되도록 sample 표시
      if (!(arg instanceof File) && !(arg && arg.ax) && !base.searchParams.has("sample")) {
        base.searchParams.set("sample", "0");
      }
      frame.onload = deliver;
      frame.src = "about:blank";
      requestAnimationFrame(() => {
        frame.src = base.href;
        if (!dialog.open) dialog.showModal();
      });
    },
  };

  window.addEventListener("message", (e) => {
    if (e.origin !== origin() || e.source !== frame?.contentWindow) return;
    if (e.data?.type === "contract-review-close") dialog.close();
  });
})();
