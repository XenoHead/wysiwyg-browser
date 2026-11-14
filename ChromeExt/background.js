// The function that will be injected into the page
// Self-update: the installer ships ChromeExt into C:\FYRTOOLS\WYSIWYG\ChromeExt.
// Client machines load that folder straight off the LAN share
// (\\<server>\FYRTOOLS\WYSIWYG\ChromeExt), so replacing the files on the server is
// the only deployment step. Chrome keeps whatever it registered at load time,
// though, so we compare the version Chrome actually loaded (the manifest held in
// memory) against version.json as it exists on disk *right now*. Once the server
// copy carries a newer version, each client reloads itself on the next poll --
// no manual "Reload" click needed.
//
// Comparing against the app's /api/extension-version instead would be wrong here:
// when both copies live on the share they always match (so it would never fire),
// and a client running a stale local WYSIWYG.exe would reload forever.
const RELOAD_CHECK_MINUTES = 5;

function getLoadedVersion() {
    try {
        return chrome.runtime.getManifest().version;
    } catch (e) {
        return null;
    }
}

function getOnDiskVersion() {
    // cache: "no-store" so an SMB copy refreshed by the installer is seen at once.
    return fetch(chrome.runtime.getURL("version.json"), { cache: "no-store" })
        .then(r => r.json())
        .then(j => j.version)
        .catch(() => null);
}

function checkForUpdate() {
    Promise.all([getLoadedVersion(), getOnDiskVersion()])
        .then(([loaded, onDisk]) => {
            if (loaded && onDisk && loaded !== onDisk) {
                console.log(`WYSIWYG Extension: ${loaded} -> ${onDisk}, reloading.`);
                chrome.runtime.reload();
            }
        })
        .catch(() => {});
}

chrome.alarms.create("extVersionCheck", { periodInMinutes: RELOAD_CHECK_MINUTES });
chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === "extVersionCheck") checkForUpdate();
});
// Also check shortly after install/startup.
setTimeout(checkForUpdate, 8000);

function triggerScrape(url) {
    const urlInput = document.getElementById('discogsUrlInput');
    const scrapeBtn = document.getElementById('scrapeBtn');

    if (urlInput && scrapeBtn) {
        urlInput.value = url;
        // Dispatch input event to ensure any listeners catch the change
        urlInput.dispatchEvent(new Event('input', { bubbles: true }));
        scrapeBtn.click();
        console.log("WYSIWYG Extension: Scrape triggered for " + url);
    } else {
        console.error("WYSIWYG Extension: Could not find input or button.");
    }
}

// Copy text to the Windows clipboard. Primary path is the service-worker
// Async Clipboard API (fires from the context-menu user gesture). If that is
// unavailable, fall back to injecting a copy into the active tab (needs the
// activeTab permission, which is granted when the menu item is clicked).
function copyToClipboard(text, tabId) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(
                () => console.log("WYSIWYG Extension: link copied to clipboard: " + text),
                (e) => {
                    console.warn("WYSIWYG Extension: SW clipboard failed, trying inject:", e);
                    injectCopy(text, tabId);
                }
            );
            return;
        }
    } catch (e) {
        console.warn("WYSIWYG Extension: clipboard unavailable in SW:", e);
    }
    injectCopy(text, tabId);
}

function injectCopy(text, tabId) {
    if (tabId == null) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId },
        func: (t) => { try { navigator.clipboard.writeText(t); } catch (e) {} },
        args: [text]
    }).catch((e) => console.warn("WYSIWYG Extension: clipboard inject failed:", e));
}

// --- Context menus ---------------------------------------------------------
// The page-level entry is context aware: on a Discogs marketplace *listing*
// page (/shop/item/<id>) it becomes "Send to Amazon Add" and hands the listing
// URL to the Amazon Adds page. Everywhere else it stays the WYSIWYG scraper.
const PAGE_MENU_ID = "sendToWysiwygPage";
const PAGE_MENU_SCRAPER_TITLE = "Send Page to WYSIWYG Scraper";
const PAGE_MENU_AMAZON_TITLE = "Send to Amazon Add";

const DISCOGS_PAGE_PATTERNS = [
    "*://*.discogs.com/release/*",
    "*://*.discogs.com/sell/item/*",
    "*://*.discogs.com/shop/item/*",
    "*://*.discogs.com/master/*"
];

// The Adds page is served by the local app (not opened as a file:// path) so its
// relative /api/adds/amazon-scrape call resolves against the running backend.
const AMAZON_ADD_PAGE = "http://127.0.0.1:8008/adds/amazon";

// Only real marketplace listing pages (/shop/item/<id>) switch the menu over.
function isShopItemUrl(url) {
    if (!url) return false;
    try {
        const u = new URL(url);
        return /(^|\.)discogs\.com$/i.test(u.hostname) && /^\/shop\/item\/\d+/.test(u.pathname);
    } catch (e) {
        return false;
    }
}

function createMenus() {
    // A duplicate id (service worker restart / re-install) is harmless: the
    // existing item is kept and only its title is refreshed by syncPageMenu().
    chrome.contextMenus.create({
        id: "sendToWysiwyg",
        title: "Send to WYSIWYG Scraper",
        contexts: ["link"],
        targetUrlPatterns: DISCOGS_PAGE_PATTERNS
    }, () => { void chrome.runtime.lastError; });

    chrome.contextMenus.create({
        id: PAGE_MENU_ID,
        title: PAGE_MENU_SCRAPER_TITLE,
        contexts: ["page"],
        documentUrlPatterns: DISCOGS_PAGE_PATTERNS
    }, () => { void chrome.runtime.lastError; });
}

function syncPageMenu(tab) {
    const url = tab && (tab.url || tab.pendingUrl);
    const title = isShopItemUrl(url) ? PAGE_MENU_AMAZON_TITLE : PAGE_MENU_SCRAPER_TITLE;
    chrome.contextMenus.update(PAGE_MENU_ID, { title: title }, () => { void chrome.runtime.lastError; });
}

function syncPageMenuFromActiveTab() {
    chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => {
        if (tabs && tabs.length) syncPageMenu(tabs[0]);
    });
}

// Make sure the menus exist, then retitle for whatever tab is showing.
function ensureMenus() {
    chrome.contextMenus.update(PAGE_MENU_ID, { title: PAGE_MENU_SCRAPER_TITLE }, () => {
        if (chrome.runtime.lastError) createMenus();
        syncPageMenuFromActiveTab();
    });
}

chrome.runtime.onInstalled.addListener(() => {
    createMenus();
    syncPageMenuFromActiveTab();
});
chrome.runtime.onStartup.addListener(ensureMenus);
ensureMenus();

// Keep the menu in step with the tab the user is looking at.
chrome.tabs.onActivated.addListener((activeInfo) => {
    chrome.tabs.get(activeInfo.tabId, (tab) => {
        if (chrome.runtime.lastError) return;
        syncPageMenu(tab);
    });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.url || changeInfo.status === "complete") syncPageMenu(tab);
});

// Open the Amazon Adds page in its own popup window (same shape the app's
// window.open() uses), pre-loaded with the listing URL. The page reads ?url=
// on load and scrapes it automatically.
//
// Only an Adds page that is *already* in a popup window is reused. A copy that
// is sitting in an ordinary tab is ignored -- reusing it would navigate that tab
// and the page would come back as a tab, not a window.
const AMAZON_ADD_TAB_RE = /^https?:\/\/(127\.0\.0\.1|localhost):8008\/adds\/amazon(\/|\?|$)/i;

function findAmazonAddWindow(callback) {
    chrome.windows.getAll({ populate: true }, (wins) => {
        if (chrome.runtime.lastError || !wins) return callback(null, null);
        for (const win of wins) {
            if (win.type !== "popup") continue;
            const tab = (win.tabs || []).find(t => AMAZON_ADD_TAB_RE.test(t.url || ""));
            if (tab) return callback(win, tab);
        }
        callback(null, null);
    });
}

function openAmazonAdd(discogsUrl, tab) {
    const target = AMAZON_ADD_PAGE + "?url=" + encodeURIComponent(discogsUrl);
    copyToClipboard(discogsUrl, tab && tab.id);

    findAmazonAddWindow((win, existing) => {
        if (win && existing) {
            chrome.tabs.update(existing.id, { url: target, active: true });
            chrome.windows.update(win.id, { focused: true });
            return;
        }
        chrome.windows.create({
            url: target,
            type: "popup",
            width: 820,
            height: 860,
            focused: true
        });
    });
}

// Find the tab where the main app page is running. Adds pages (/adds/...) share
// the host, so prefer the main page rather than whatever 8008 tab comes first.
function findAppTab(callback) {
    chrome.tabs.query({ url: ["http://127.0.0.1:8008/*", "http://localhost:8008/*"] }, (tabs) => {
        if (!tabs || !tabs.length) return callback(null);
        const main = tabs.find(t =>
            /^https?:\/\/(127\.0\.0\.1|localhost):8008\/(index\.html)?([?#]|$)/i.test(t.url || ""));
        callback(main || tabs[0]);
    });
}

// Bring the local app tab to the front. In desktop mode no such tab exists --
// the app raises its own window from main.py's scrape bridge instead.
function focusAppTab() {
    findAppTab((target) => {
        if (!target) return;
        chrome.tabs.update(target.id, { active: true });
        if (target.windowId != null) chrome.windows.update(target.windowId, { focused: true });
    });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
    const isLinkScrape = info.menuItemId === "sendToWysiwyg" && info.linkUrl;
    const isPageScrape = info.menuItemId === PAGE_MENU_ID;

    // Marketplace listing page: route to Adds > Amazon instead of the scraper.
    if (isPageScrape) {
        const pageUrl = info.pageUrl || (tab && (tab.url || tab.pendingUrl));
        if (isShopItemUrl(pageUrl)) {
            openAmazonAdd(pageUrl, tab);
            return;
        }
    }

    if (isLinkScrape || isPageScrape) {
        const targetUrl = isPageScrape ? (info.pageUrl || tab.url) : info.linkUrl;
        if (!targetUrl) return;

        // Copy the Discogs link to the Windows clipboard.
        copyToClipboard(targetUrl, tab.id);

        // Try local native app API first
        fetch('http://127.0.0.1:8008/api/extension-scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: targetUrl })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error("Local API request failed");
            }
            console.log("URL sent to WYSIWYG native desktop window successfully.");
            // Hand focus to the app so the scrape result is on screen.
            focusAppTab();
        })
        .catch(err => {
            console.log("Could not reach native app via API, falling back to tab injection:", err);
            
            // Helper to inject the script
            const runScript = (tabId) => {
                chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    func: triggerScrape,
                    args: [targetUrl]
                }).catch(err => console.error("Script injection failed:", err));
            };

            // Find the tab where the WYSIWYG tool is running
            findAppTab((wysiwygTab) => {
                if (wysiwygTab) {
                    chrome.tabs.update(wysiwygTab.id, { active: true });
                    chrome.windows.update(wysiwygTab.windowId, { focused: true });
                    runScript(wysiwygTab.id);
                } else {
                    // If the tab isn't open, open it and then send the message
                    chrome.tabs.create({ url: "http://127.0.0.1:8008/" }, (newTab) => {
                        // Wait for the tab to finish loading before sending the message
                        chrome.tabs.onUpdated.addListener(function listener(tabId, changeInfo) {
                            if (tabId === newTab.id && changeInfo.status === 'complete') {
                                chrome.tabs.onUpdated.removeListener(listener); // Clean up the listener
                                // Small delay to ensure DOM is ready
                                setTimeout(() => runScript(newTab.id), 500);
                            }
                        });
                    });
                }
            });
        });
    }
});