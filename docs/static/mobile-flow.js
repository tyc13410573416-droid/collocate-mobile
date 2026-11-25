/* Mobile changes views, never input data or the backend gate decision. */
(() => {
  const breakpoint = window.matchMedia("(max-width: 820px)");
  const byId = id => document.getElementById(id);
  const body = document.body;
  const back = byId("mobileBack");
  const original = byId("mobileOriginal");
  const relocations = [
    [byId("reportIdField"), byId("mobileOptionsSlot")],
    [byId("medicationField"), byId("mobileOptionsSlot")],
    [document.querySelector(".sample-row"), byId("mobileExamplesSlot")],
    [byId("gateDemoPicker"), byId("mobileExamplesSlot")],
    [byId("assetPreview"), byId("mobileOriginalSlot")],
    [document.querySelector(".mobile-submit-bar"), body],
  ].map(([element, target]) => {
    const home = document.createComment(`mobile-home:${element.id || element.className}`);
    element.before(home);
    return { element, target, home };
  });
  let view = "input";
  let phase = "input";
  let busy = false;
  let navigationFrame;

  function sync() {
    body.dataset.mobileView = view;
    body.dataset.mobilePhase = phase;
    back.hidden = view !== "result";
    back.disabled = busy;
    byId("mobileRetry").disabled = busy;
    byId("mobileStepStatus").textContent = view === "input" ? "先准备一份报告"
      : busy ? "正在处理，请稍候" : phase === "error" ? "请求未完成，可重试" : "核对结果与来源";
    ["mobileInputStep", "mobileResultStep"].forEach((id, index) => {
      const item = byId(id);
      const active = (view === "input" ? 0 : 1) === index;
      if (active) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
    relocations.forEach(({ element, target, home }) => {
      const move = breakpoint.matches && (element.id !== "assetPreview" || view === "result");
      if (move) target.append(element);
      else home.after(element);
    });
    const hasImage = !byId("assetPreview").classList.contains("hidden");
    original.hidden = !hasImage;
    byId("mobileErrorActions").classList.toggle("hidden", phase !== "error");
    byId("outputViewTitle").textContent = phase === "loading" ? "正在解读报告" : "带来源解读";
  }

  function reveal(titleId) {
    if (!breakpoint.matches) return;
    cancelAnimationFrame(navigationFrame);
    navigationFrame = requestAnimationFrame(() => {
      // Avoid a smooth scroll through the input form, and do not steal modal focus.
      if (!document.querySelector("dialog[open]")) byId(titleId)?.focus({ preventScroll: true });
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    });
  }

  function input({ scroll = true } = {}) {
    if (busy) return;
    view = "input";
    phase = "input";
    original.open = false;
    sync();
    // A hidden textarea has scrollHeight=0; recalculate after moving it into view.
    resizeInputTextareas();
    if (scroll) reveal("inputViewTitle");
  }

  window.MEDTRACE_FLOW = {
    isMobile: () => breakpoint.matches,
    input,
    start() {
      view = "result";
      phase = "loading";
      original.open = false;
      sync();
      reveal("outputViewTitle");
    },
    result() {
      view = "result";
      phase = "ready";
      sync();
      reveal("outputViewTitle");
    },
    error() {
      view = "result";
      phase = "error";
      sync();
      reveal("outputViewTitle");
    },
    busy(value) { busy = value; sync(); },
  };

  back.addEventListener("click", () => input());
  byId("mobileRetry").addEventListener("click", () => { if (!busy) form.requestSubmit(); });
  document.querySelector(".site-brand").addEventListener("click", event => {
    if (!breakpoint.matches) return;
    event.preventDefault();
    input();
  });
  breakpoint.addEventListener("change", () => {
    sync();
    resizeInputTextareas();
    if (breakpoint.matches) reveal(view === "input" ? "inputViewTitle" : "outputViewTitle");
  });
  body.classList.add("has-mobile-flow");
  sync();
  // The original upload preview remains available alongside the mobile review editor.
  new MutationObserver(() => { original.hidden = byId("assetPreview").classList.contains("hidden"); })
    .observe(byId("assetPreview"), { attributes: true, attributeFilter: ["class"] });
})();
