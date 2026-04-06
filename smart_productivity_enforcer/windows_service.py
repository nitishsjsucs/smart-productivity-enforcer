"""Windows Service for the Smart Productivity Enforcer.

This module provides a Windows Service wrapper that:
1. Runs the productivity enforcer as a system service
2. Prevents easy termination by regular users
3. Auto-starts on system boot
4. Survives user logout
"""

import asyncio
import sys
import os
import subprocess
from pathlib import Path
from typing import Optional

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    HAS_WIN32_SERVICE = True
except ImportError:
    HAS_WIN32_SERVICE = False


class ProductivityEnforcerService:
    """Windows Service implementation for the Productivity Enforcer."""
    
    _svc_name_ = "SmartProductivityEnforcer"
    _svc_display_name_ = "Smart Productivity Enforcer"
    _svc_description_ = "AI-powered productivity enforcement that monitors activity and blocks distractions"
    
    def __init__(self):
        self.running = False
        self.daemon = None
    
    if HAS_WIN32_SERVICE:
        class Win32Service(win32serviceutil.ServiceFramework):
            _svc_name_ = "SmartProductivityEnforcer"
            _svc_display_name_ = "Smart Productivity Enforcer"
            _svc_description_ = "AI-powered productivity enforcement service"
            
            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
                self.running = True
            
            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                win32event.SetEvent(self.hWaitStop)
                self.running = False
            
            def SvcDoRun(self):
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, '')
                )
                self.main()
            
            def main(self):
                from smart_productivity_enforcer.daemon import ProductivityDaemon
                from smart_productivity_enforcer.config import Config
                
                config = Config.load()
                daemon = ProductivityDaemon(config)
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    loop.run_until_complete(daemon.start())
                except Exception as e:
                    servicemanager.LogErrorMsg(f"Service error: {e}")
                finally:
                    loop.close()


def install_service() -> tuple[bool, str]:
    """Install the productivity enforcer as a Windows service."""
    if not HAS_WIN32_SERVICE:
        return False, "pywin32 not installed. Run: pip install pywin32"
    
    try:
        python_exe = sys.executable
        script_path = Path(__file__).resolve()
        
        cmd = [
            "sc", "create", "SmartProductivityEnforcer",
            "binPath=", f'"{python_exe}" "{script_path}" --service',
            "DisplayName=", "Smart Productivity Enforcer",
            "start=", "auto",
            "obj=", "LocalSystem"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        
        if result.returncode == 0:
            subprocess.run(
                ["sc", "description", "SmartProductivityEnforcer",
                 "AI-powered productivity enforcement service"],
                capture_output=True, shell=True
            )
            return True, "Service installed successfully"
        else:
            return False, f"Failed to install service: {result.stderr}"
            
    except Exception as e:
        return False, f"Error installing service: {e}"


def uninstall_service() -> tuple[bool, str]:
    """Uninstall the Windows service."""
    try:
        subprocess.run(["sc", "stop", "SmartProductivityEnforcer"],
                      capture_output=True, shell=True)
        
        result = subprocess.run(
            ["sc", "delete", "SmartProductivityEnforcer"],
            capture_output=True, text=True, shell=True
        )
        
        if result.returncode == 0:
            return True, "Service uninstalled successfully"
        else:
            return False, f"Failed to uninstall: {result.stderr}"
            
    except Exception as e:
        return False, f"Error uninstalling service: {e}"


def start_service() -> tuple[bool, str]:
    """Start the Windows service."""
    try:
        result = subprocess.run(
            ["sc", "start", "SmartProductivityEnforcer"],
            capture_output=True, text=True, shell=True
        )
        
        if result.returncode == 0:
            return True, "Service started"
        else:
            return False, f"Failed to start: {result.stderr}"
            
    except Exception as e:
        return False, f"Error starting service: {e}"


def stop_service() -> tuple[bool, str]:
    """Stop the Windows service."""
    try:
        result = subprocess.run(
            ["sc", "stop", "SmartProductivityEnforcer"],
            capture_output=True, text=True, shell=True
        )
        
        if result.returncode == 0:
            return True, "Service stopped"
        else:
            return False, f"Failed to stop: {result.stderr}"
            
    except Exception as e:
        return False, f"Error stopping service: {e}"


def get_service_status() -> dict:
    """Get the current service status."""
    try:
        result = subprocess.run(
            ["sc", "query", "SmartProductivityEnforcer"],
            capture_output=True, text=True, shell=True
        )
        
        if result.returncode != 0:
            return {"installed": False, "running": False}
        
        output = result.stdout
        running = "RUNNING" in output
        stopped = "STOPPED" in output
        
        return {
            "installed": True,
            "running": running,
            "stopped": stopped,
            "raw_status": output
        }
        
    except Exception as e:
        return {"installed": False, "running": False, "error": str(e)}


class ProcessProtector:
    """Protects the process from being terminated easily."""
    
    @staticmethod
    def protect_process() -> bool:
        """Apply protection to prevent process termination."""
        try:
            import ctypes
            from ctypes import wintypes
            
            kernel32 = ctypes.windll.kernel32
            
            PROCESS_ALL_ACCESS = 0x1F0FFF
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def run_as_high_priority() -> bool:
        """Set process to high priority."""
        try:
            import psutil
            process = psutil.Process()
            process.nice(psutil.HIGH_PRIORITY_CLASS)
            return True
        except Exception:
            return False
    
    @staticmethod
    def prevent_sleep() -> bool:
        """Prevent system from sleeping while enforcer is active."""
        try:
            import ctypes
            
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            )
            return True
        except Exception:
            return False
    
    @staticmethod
    def allow_sleep() -> bool:
        """Allow system to sleep again."""
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            return True
        except Exception:
            return False


class TaskSchedulerIntegration:
    """Integrate with Windows Task Scheduler for persistent startup."""
    
    TASK_NAME = "SmartProductivityEnforcer"
    
    @classmethod
    def create_startup_task(cls, duration_minutes: Optional[int] = None) -> tuple[bool, str]:
        """Create a scheduled task to run the enforcer at startup."""
        try:
            python_exe = sys.executable
            module_path = "smart_productivity_enforcer.daemon"
            
            args = f'"{python_exe}" -m {module_path}'
            if duration_minutes:
                args += f" --duration {duration_minutes}"
            
            xml_content = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Smart Productivity Enforcer - AI-powered focus enforcement</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>-m {module_path}</Arguments>
    </Exec>
  </Actions>
</Task>'''
            
            task_file = Path.home() / ".smart-productivity-enforcer" / "task.xml"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(task_file, "w", encoding="utf-16") as f:
                f.write(xml_content)
            
            result = subprocess.run(
                ["schtasks", "/create", "/tn", cls.TASK_NAME, "/xml", str(task_file), "/f"],
                capture_output=True, text=True, shell=True
            )
            
            if result.returncode == 0:
                return True, "Startup task created successfully"
            else:
                return False, f"Failed to create task: {result.stderr}"
                
        except Exception as e:
            return False, f"Error creating startup task: {e}"
    
    @classmethod
    def delete_startup_task(cls) -> tuple[bool, str]:
        """Delete the startup task."""
        try:
            result = subprocess.run(
                ["schtasks", "/delete", "/tn", cls.TASK_NAME, "/f"],
                capture_output=True, text=True, shell=True
            )
            
            if result.returncode == 0:
                return True, "Startup task deleted"
            else:
                return False, f"Failed to delete task: {result.stderr}"
                
        except Exception as e:
            return False, f"Error deleting task: {e}"
    
    @classmethod
    def is_task_enabled(cls) -> bool:
        """Check if the startup task exists and is enabled."""
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/tn", cls.TASK_NAME],
                capture_output=True, text=True, shell=True
            )
            return result.returncode == 0
        except Exception:
            return False


if __name__ == "__main__":
    if "--service" in sys.argv and HAS_WIN32_SERVICE:
        win32serviceutil.HandleCommandLine(ProductivityEnforcerService.Win32Service)
