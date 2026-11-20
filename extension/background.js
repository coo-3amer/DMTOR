// MZ-DManager Lite — browser bridge (Windows 7 edition, files only)
const APP = "http://127.0.0.1:9615";
const bypass = new Set(); // URLs the browser should download itself (app refused them)

async function settings() {
  const s = await chrome.storage.local.get({ intercept: true, onlyClicks: true, minSizeKB: 0 });
  return s;
}

// A download counts as "yours" only if you clicked something in a page shortly before it started.
// (Sites often make you wait a few seconds after clicking "Download", hence the window.)
const CLICK_WINDOW_MS = 20000;

async function clickedRecently() {
  try {
    const { lastClick = 0 } = await chrome.storage.session.get("lastClick");
    return Date.now() - lastClick < CLICK_WINDOW_MS;
  } catch (e) {
    return true;   // can't tell → don't block anything
  }
}

// { alive, capture } — capture is the "Catching on/off" switch in the app
async function appStatus() {
  try {
    const r = await fetch(APP + "/ping", { signal: AbortSignal.timeout(800) });
    if (!r.ok) return { alive: false, capture: false };
    const j = await r.json();
    return { alive: true, capture: j.capture !== false };
  } catch (e) {
    return { alive: false, capture: false };
  }
}

async function appAlive() {
  return (await appStatus()).alive;
}

async function cookieHeader(url) {
  try {
    const cs = await chrome.cookies.getAll({ url });
    return cs.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    return "";
  }
}

async function sendToApp(payload) {
  try {
    const r = await fetch(APP + "/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userAgent: navigator.userAgent, ...payload }),
    });
    return r.ok;
  } catch (e) {
    return false;
  }
}

function baseName(p) {
  return (p || "").split(/[\\/]/).pop();
}

// 1) Catch every download the browser starts and hand it to the app
chrome.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url)) return;            // blob:, data: etc. stay in the browser
  if (bypass.has(url)) { bypass.delete(url); return; }
  const s = await settings();
  if (!s.intercept) return;
  if (s.onlyClicks && !(await clickedRecently())) return;   // the site started it by itself → leave it to the browser
  const size = item.totalBytes > 0 ? item.totalBytes : item.fileSize;
  const name = baseName(item.filename).toLowerCase();
  if (s.minSizeKB && size > 0 && size < s.minSizeKB * 1024) return;
  const st = await appStatus();
  if (!st.alive || !st.capture) return;          // app closed or catching switched off → browser downloads normally

  try { await chrome.downloads.cancel(item.id); } catch (e) {}
  try { await chrome.downloads.erase({ id: item.id }); } catch (e) {}

  const ok = await sendToApp({
    type: "file",
    url,
    referrer: item.referrer || "",
    filename: baseName(item.filename),
    mime: item.mime || "",
    size: size > 0 ? size : 0,
    cookies: await cookieHeader(url),
  });
  if (!ok) {
    bypass.add(url);
    chrome.downloads.download({ url });
  }
});

// 2) Right-click menu
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "mzl-link", title: "Download link with MZ-DManager Lite", contexts: ["link", "image", "audio", "video"] });
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  const url = info.linkUrl || info.srcUrl;
  if (!url || !/^https?:/i.test(url)) return;
  await sendToApp({ type: "file", url, referrer: info.pageUrl || "", cookies: await cookieHeader(url) });
});

// 3) Messages from the page (clicks) and the popup
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.action === "click") {
      try { await chrome.storage.session.set({ lastClick: Date.now() }); } catch (e) {}
      reply({ ok: true });
    } else if (msg.action === "status") {
      reply(await appStatus());
    }
  })();
  return true; // async reply
});
