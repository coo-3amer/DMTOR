// Remember that *you* clicked something (in any frame), so MZ-DManager only catches downloads you start.
(() => {
  let lastSent = 0;
  const noteClick = (e) => {
    if (e && e.isTrusted === false) return;          // ignore clicks faked by the page's own scripts
    const now = Date.now();
    if (now - lastSent < 1000) return;
    lastSent = now;
    try { chrome.runtime.sendMessage({ action: "click" }); } catch (err) {}
  };
  document.addEventListener("mousedown", noteClick, true);
  document.addEventListener("contextmenu", noteClick, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") noteClick(e); }, true);
})();
