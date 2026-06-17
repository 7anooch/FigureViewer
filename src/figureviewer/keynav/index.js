(() => {
  const rootDoc = (typeof window !== "undefined" && window.parent && window.parent.document)
    ? window.parent.document
    : document;

  let armed = true;

  function shouldIgnoreTarget(el) {
    if (!el) return true;
    const sidebar = rootDoc.querySelector('[data-testid="stSidebar"]');
    if (sidebar && sidebar.contains(el)) return true;
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function onKeyDown(e) {
    if (!armed) return;
    if (shouldIgnoreTarget(e.target)) return;

    const map = {
      ArrowLeft: "prev",
      ArrowRight: "next",
      Home: "first",
      End: "last",
    };
    const id = map[e.code];
    if (!id) return;

    e.preventDefault();
    e.stopPropagation();

    Streamlit.setComponentValue({
      id,
      code: e.code,
      ts: Date.now(),
    });
  }

  window.addEventListener("load", () => {
    rootDoc.addEventListener("keydown", onKeyDown, { passive: false });
    Streamlit.setComponentReady();
    Streamlit.setFrameHeight(0);
  });

  Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, (event) => {
    const args = (event && event.detail && event.detail.args) || {};
    armed = args.armed !== false;
    Streamlit.setFrameHeight(0);
  });

  window.addEventListener("beforeunload", () => {
    rootDoc.removeEventListener("keydown", onKeyDown, { passive: false });
  });
})();
