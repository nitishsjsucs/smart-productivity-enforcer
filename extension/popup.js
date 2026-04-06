// Popup script
document.addEventListener('DOMContentLoaded', async () => {
  const statusDiv = document.getElementById('status');
  const statusText = document.getElementById('status-text');
  const reconnectBtn = document.getElementById('reconnect');

  // Check connection status
  async function checkStatus() {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'get_status' });
      updateUI(response?.connected || false);
    } catch (e) {
      updateUI(false);
    }
  }

  function updateUI(connected) {
    if (connected) {
      statusDiv.className = 'status connected';
      statusText.textContent = 'Connected to Enforcer';
    } else {
      statusDiv.className = 'status disconnected';
      statusText.textContent = 'Disconnected';
    }
  }

  reconnectBtn.addEventListener('click', async () => {
    try {
      await chrome.runtime.sendMessage({ type: 'reconnect' });
      setTimeout(checkStatus, 1000);
    } catch (e) {
      console.error('Failed to reconnect:', e);
    }
  });

  checkStatus();
});
