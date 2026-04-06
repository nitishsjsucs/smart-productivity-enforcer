"""Integration with Windows-Use for advanced Windows automation."""

import asyncio
import sys
from pathlib import Path
from typing import Optional, Any

WINDOWS_USE_PATH = Path(__file__).parent.parent.parent.parent / "Windows-Use"
if str(WINDOWS_USE_PATH) not in sys.path:
    sys.path.insert(0, str(WINDOWS_USE_PATH))

try:
    from windows_use.agent import Agent, Browser
    from windows_use.uia import UIAutomation
    HAS_WINDOWS_USE = True
except ImportError:
    HAS_WINDOWS_USE = False
    Agent = None
    Browser = None


class WindowsUseIntegration:
    """Integration with Windows-Use for advanced Windows automation."""
    
    def __init__(self):
        self.agent: Optional[Any] = None
        self._initialized = False
    
    def is_available(self) -> bool:
        """Check if Windows-Use is available."""
        return HAS_WINDOWS_USE
    
    async def initialize(self, llm_config: dict) -> bool:
        """Initialize the Windows-Use agent."""
        if not HAS_WINDOWS_USE:
            return False
        
        try:
            from windows_use.llms.google import ChatGoogle
            import os
            
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return False
            
            llm = ChatGoogle(
                model=llm_config.get("model", "gemini-2.0-flash"),
                api_key=api_key,
                temperature=llm_config.get("temperature", 0.3)
            )
            
            self.agent = Agent(
                llm=llm,
                browser=Browser.EDGE,
                use_vision=False,
                auto_minimize=False
            )
            
            self._initialized = True
            return True
            
        except Exception as e:
            print(f"Failed to initialize Windows-Use: {e}")
            return False
    
    async def get_ui_tree(self) -> Optional[dict]:
        """Get the UI automation tree of the current window."""
        if not HAS_WINDOWS_USE:
            return None
        
        try:
            from windows_use.uia import UIAutomation
            uia = UIAutomation()
            
            return None
            
        except Exception as e:
            print(f"Error getting UI tree: {e}")
            return None
    
    async def execute_action(self, action: str) -> Optional[str]:
        """Execute an action using Windows-Use agent."""
        if not self._initialized or not self.agent:
            return None
        
        try:
            response = self.agent.run(query=action)
            return str(response)
        except Exception as e:
            return f"Error: {e}"
    
    async def close_application(self, app_name: str) -> bool:
        """Close an application using Windows-Use."""
        if not self._initialized:
            return False
        
        try:
            action = f"Close the {app_name} application window"
            await self.execute_action(action)
            return True
        except Exception:
            return False
    
    async def focus_window(self, window_title: str) -> bool:
        """Focus a specific window."""
        if not self._initialized:
            return False
        
        try:
            action = f"Click on the window titled '{window_title}' to bring it to focus"
            await self.execute_action(action)
            return True
        except Exception:
            return False


class UIElementFinder:
    """Find and interact with UI elements using UI Automation."""
    
    def __init__(self):
        self._uia = None
    
    def is_available(self) -> bool:
        """Check if UI Automation is available."""
        try:
            import uiautomation
            return True
        except ImportError:
            return False
    
    def find_element_by_name(self, name: str) -> Optional[Any]:
        """Find a UI element by its name."""
        try:
            import uiautomation as auto
            element = auto.WindowControl(searchDepth=1, Name=name)
            if element.Exists():
                return element
            return None
        except Exception:
            return None
    
    def get_all_windows(self) -> list[dict]:
        """Get information about all open windows."""
        try:
            import uiautomation as auto
            
            windows = []
            for win in auto.GetRootControl().GetChildren():
                if win.ControlType == auto.ControlType.WindowControl:
                    windows.append({
                        "name": win.Name,
                        "class_name": win.ClassName,
                        "automation_id": win.AutomationId,
                    })
            return windows
        except Exception:
            return []
    
    def click_button(self, window_name: str, button_name: str) -> bool:
        """Click a button within a window."""
        try:
            import uiautomation as auto
            
            window = auto.WindowControl(searchDepth=1, Name=window_name)
            if not window.Exists():
                return False
            
            button = window.ButtonControl(Name=button_name)
            if button.Exists():
                button.Click()
                return True
            return False
        except Exception:
            return False
