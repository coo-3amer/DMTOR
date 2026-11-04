// Floating "Download video" button, shown when the page has a visible video.
(() => {
  if (window.top !== window) return;
  let host = null, label = null;
  let enabled = true;
  let hiddenByUser = false;

  let magnets = true;
  chrome.storage.local.get({ videoButton: true, magnets: true }, (s) => {
    enabled = s.videoButton;
    magnets = s.magnets;
  });
  chrome.storage.onChanged.addListener((c) => {
    if (c.videoButton) enabled = c.videoButton.newValue;
    if (c.magnets) magnets = c.magnets.newValue;
  });

  // Magnet links: send to the app instead of asking which program to open.
  document.addEventListener("click", (e) => {
    if (!magnets || e.defaultPrevented || e.button !== 0) return;
    const a = e.target && e.target.closest ? e.target.closest('a[href^="magnet:"]') : null;
    if (!a) return;
    e.preventDefault();
    e.stopPropagation();
    chrome.runtime.sendMessage({ action: "torrent", url: a.href }, (res) => {
      if (!(res && res.ok)) window.location.href = a.href; // app closed: fall back to the browser
    });
  }, true);

  const ARROW = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 20h14"/></svg>';
  const CLOSE = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';
  const TEXT = "Download video";

  function make() {
    host = document.createElement("div");
    const root = host.attachShadow({ mode: "closed" }); // isolate from the page's CSS
    root.innerHTML = `
      <style>
        .b { position:fixed; top:84px; right:18px; z-index:2147483647; display:flex; align-items:center;
             gap:8px; padding:9px 12px 9px 14px; border-radius:999px; cursor:pointer; user-select:none;
             background:#3b82f6; color:#ffffff; font:600 13px/1 "Segoe UI",system-ui,sans-serif;
             box-shadow:0 6px 20px rgba(0,0,0,.35); transition:transform .15s, background .15s; }
        .b:hover { background:#5a97f8; transform:translateY(-1px); }
        .x { margin-left:4px; width:18px; height:18px; border-radius:50%; display:grid; place-items:center;
             font-size:11px; opacity:.6; }
        .x:hover { opacity:1; background:rgba(0,0,0,.12); }
        .ok { background:#1b1f26; color:#e6e8eb; }
        .warn { background:#3a2a12; color:#ffd59a; }
      </style>
      <div class="b"><span class="i">${ARROW}</span><span class="t">${TEXT}</span><span class="x" title="Hide">${CLOSE}</span></div>`;
    const btn = root.querySelector(".b");
    label = root.querySelector(".t");
    root.querySelector(".x").addEventListener("click", (e) => {
      e.stopPropagation();
      hiddenByUser = true;
      host.style.display = "none";
    });
    btn.addEventListener("click", () => {
      label.textContent = "Sending\u2026";
      chrome.runtime.sendMessage({ action: "video", url: location.href, title: document.title }, (res) => {
        btn.classList.remove("ok", "warn");
        if (res && res.ok) { label.textContent = "Sent to EDENLOAD"; btn.classList.add("ok"); }
        else if (res && res.reason === "app") { label.textContent = "Open EDENLOAD first"; btn.classList.add("warn"); }
        else { label.textContent = "Something went wrong"; btn.classList.add("warn"); }
        setTimeout(() => { label.textContent = TEXT; btn.classList.remove("ok", "warn"); }, 2500);
      });
    });
    document.documentElement.appendChild(host);
  }

  function hasBigVideo() {
    return [...document.querySelectorAll("video")].some((v) => {
      const r = v.getBoundingClientRect();
      return r.width >= 300 && r.height >= 150;
    });
  }

  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) { lastUrl = location.href; hiddenByUser = false; }
    const show = enabled && !hiddenByUser && hasBigVideo();
    if (show && !host) make();
    if (host) host.style.display = show ? "block" : "none";
  }, 1500);
})();
