"""Default tool registration (spec §6, §7).

Phase 4 ships the foundational set: filesystem (list/stat/read/mkdir/write),
process (list/info), system (info), and shell (execute). Roadmap Phase C adds
the network set: network.fetch (bounded read-only HTTP GET), homeassistant
states (read-only) + call (acts on the home, always ASK-gated). Laptop
control adds the gui set: screenshot (metadata unless saved) + click/type
(acts on the machine, always ASK-gated). Reserved categories (BROWSER) and
tools (filesystem delete, process terminate) are intentionally absent.
"""

from __future__ import annotations

from jarvis.tools.filesystem_tools import (
    FilesystemListTool,
    FilesystemMkdirTool,
    FilesystemReadTool,
    FilesystemStatTool,
    FilesystemWriteTool,
)
from jarvis.tools.gui_tools import GuiClickTool, GuiScreenshotTool, GuiTypeTool
from jarvis.tools.homeassistant_tools import HomeAssistantCallTool, HomeAssistantStatesTool
from jarvis.tools.network_tools import NetworkFetchTool
from jarvis.tools.process_tools import ProcessInfoTool, ProcessListTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.shell_tools import ShellExecuteTool
from jarvis.tools.system_tools import SystemInfoTool

DEFAULT_TOOL_CLASSES: tuple[type, ...] = (
    FilesystemListTool,
    FilesystemStatTool,
    FilesystemReadTool,
    FilesystemMkdirTool,
    FilesystemWriteTool,
    ProcessListTool,
    ProcessInfoTool,
    SystemInfoTool,
    ShellExecuteTool,
    NetworkFetchTool,
    HomeAssistantStatesTool,
    HomeAssistantCallTool,
    GuiScreenshotTool,
    GuiClickTool,
    GuiTypeTool,
)


def register_default_tools(registry: ToolRegistry) -> None:
    """Register every Phase 4 tool into `registry` (duplicates raise)."""
    for tool_class in DEFAULT_TOOL_CLASSES:
        registry.register(tool_class())
