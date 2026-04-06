// Smart Productivity Enforcer - Chrome Extension Background Service Worker

const SERVER_URL = 'ws://localhost:9876';
let ws = null;
let reconnectInterval = null;
let isConnected = false;

// Connect to the productivity enforcer server
function connectToServer() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }

  try {
    ws = new WebSocket(SERVER_URL);

    ws.onopen = () => {
      console.log('[SPE] Connected to productivity enforcer server');
      isConnected = true;
      clearInterval(reconnectInterval);
      reconnectInterval = null;
      
      // Send initial tab list
      sendAllTabs();
      
      // Update badge to show connected
      chrome.action.setBadgeText({ text: 'ON' });
      chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        handleServerMessage(message);
      } catch (e) {
        console.error('[SPE] Error parsing message:', e);
      }
    };

    ws.onclose = () => {
      console.log('[SPE] Disconnected from server');
      isConnected = false;
      ws = null;
      
      // Update badge to show disconnected
      chrome.action.setBadgeText({ text: 'OFF' });
      chrome.action.setBadgeBackgroundColor({ color: '#F44336' });
      
      // Try to reconnect
      if (!reconnectInterval) {
        reconnectInterval = setInterval(connectToServer, 5000);
      }
    };

    ws.onerror = (error) => {
      console.error('[SPE] WebSocket error:', error);
    };

  } catch (e) {
    console.error('[SPE] Failed to connect:', e);
  }
}

// Handle messages from the server
function handleServerMessage(message) {
  switch (message.type) {
    case 'close_tab':
      closeTab(message.tabId);
      break;
    case 'close_tabs_by_url':
      closeTabsByUrl(message.urlPattern);
      break;
    case 'get_tabs':
      sendAllTabs();
      break;
    case 'ping':
      sendMessage({ type: 'pong' });
      break;
    default:
      console.log('[SPE] Unknown message type:', message.type);
  }
}

// Send a message to the server
function sendMessage(message) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}

// Send all current tabs to the server
async function sendAllTabs() {
  try {
    const tabs = await chrome.tabs.query({});
    const tabInfo = tabs.map(tab => ({
      id: tab.id,
      url: tab.url || '',
      title: tab.title || '',
      active: tab.active,
      windowId: tab.windowId,
      favIconUrl: tab.favIconUrl || ''
    }));
    
    sendMessage({
      type: 'tabs_update',
      tabs: tabInfo,
      timestamp: Date.now()
    });
  } catch (e) {
    console.error('[SPE] Error getting tabs:', e);
  }
}

// Close a specific tab by ID
async function closeTab(tabId) {
  try {
    await chrome.tabs.remove(tabId);
    console.log(`[SPE] Closed tab ${tabId}`);
    sendMessage({ type: 'tab_closed', tabId: tabId, success: true });
  } catch (e) {
    console.error(`[SPE] Failed to close tab ${tabId}:`, e);
    sendMessage({ type: 'tab_closed', tabId: tabId, success: false, error: e.message });
  }
}

// Close tabs matching a URL pattern
async function closeTabsByUrl(urlPattern) {
  try {
    const tabs = await chrome.tabs.query({});
    const closedTabs = [];
    
    for (const tab of tabs) {
      if (tab.url && tab.url.includes(urlPattern)) {
        await chrome.tabs.remove(tab.id);
        closedTabs.push(tab.id);
        console.log(`[SPE] Closed tab matching "${urlPattern}": ${tab.url}`);
      }
    }
    
    sendMessage({
      type: 'tabs_closed_by_url',
      pattern: urlPattern,
      closedTabIds: closedTabs,
      count: closedTabs.length
    });
  } catch (e) {
    console.error(`[SPE] Error closing tabs by URL:`, e);
  }
}

// Listen for tab events
chrome.tabs.onCreated.addListener((tab) => {
  sendMessage({
    type: 'tab_created',
    tab: {
      id: tab.id,
      url: tab.url || '',
      title: tab.title || '',
      windowId: tab.windowId
    }
  });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.title) {
    sendMessage({
      type: 'tab_updated',
      tabId: tabId,
      url: tab.url || '',
      title: tab.title || '',
      changes: changeInfo
    });
  }
});

chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
  sendMessage({
    type: 'tab_removed',
    tabId: tabId,
    windowId: removeInfo.windowId
  });
});

chrome.tabs.onActivated.addListener((activeInfo) => {
  chrome.tabs.get(activeInfo.tabId, (tab) => {
    if (tab) {
      sendMessage({
        type: 'tab_activated',
        tab: {
          id: tab.id,
          url: tab.url || '',
          title: tab.title || '',
          windowId: tab.windowId
        }
      });
    }
  });
});

// Periodic tab sync (every 10 seconds)
setInterval(sendAllTabs, 10000);

// Initial connection
connectToServer();

// Handle messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'get_status') {
    sendResponse({ connected: isConnected });
  } else if (message.type === 'reconnect') {
    connectToServer();
    sendResponse({ ok: true });
  }
  return true;
});
