// The function that will be injected into the page
// Self-update: the installer ships ChromeExt into C:\FYRTOOLS\WYSIWYG\ChromeExt
// and overwrites these files on app upgrade. Because an unpacked extension only
// reloads when Chrome re-reads the folder, we poll the running app for its
// bundled extension version and call chrome.runtime.reload() when it changes.
const APP_VERSION_URL = "http://127.0.0.1:8008/api/extension-version";
const RELOAD_CHECK_MINUTES = 5;

function getInstalledVersion() {
    return fetch(chrome.runtime.getURL("version.json"))
        .then(r => r.json())
        .then(j => j.version)
        .catch(() => null);
}

function checkForUpdate() {
    Promise.all([getInstalledVersion(), fetch(APP_VERSION_URL).then(r => r.json()).then(j => j.version).catch(() => null)])
        .then(([installed, shipped]) => {
            if (installed && shipped && installed !== shipped) {
                console.log(`WYSIWYG Extension: version ${installed} -> ${shipped}, reloading.`);
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

chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: "sendToWysiwyg",
        title: "Send to WYSIWYG Scraper",
        contexts: ["link"],
        targetUrlPatterns: [
            "*://*.discogs.com/release/*",
            "*://*.discogs.com/sell/item/*",
            "*://*.discogs.com/shop/item/*",
            "*://*.discogs.com/master/*"
        ]
    });

    chrome.contextMenus.create({
        id: "sendToWysiwygPage",
        title: "Send Page to WYSIWYG Scraper",
        contexts: ["page"],
        documentUrlPatterns: [
            "*://*.discogs.com/release/*",
            "*://*.discogs.com/sell/item/*",
            "*://*.discogs.com/shop/item/*",
            "*://*.discogs.com/master/*"
        ]
    });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
    const isLinkScrape = info.menuItemId === "sendToWysiwyg" && info.linkUrl;
    const isPageScrape = info.menuItemId === "sendToWysiwygPage";

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
            chrome.tabs.query({ url: ["http://127.0.0.1:8008/*", "http://localhost:8008/*"] }, (tabs) => {
                if (tabs.length > 0) {
                    const wysiwygTab = tabs[0];
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