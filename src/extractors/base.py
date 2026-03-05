"""Base extractor ABC for all tool-specific extractors."""

from abc import ABC, abstractmethod
from typing import Dict, List


class BaseExtractor(ABC):
    @abstractmethod
    def extract_skills(self) -> List[Dict]:
        """Extract skills/commands from the tool's config files.
        Returns list of dicts matching SkillDocument fields."""
        pass

    @abstractmethod
    def extract_mcp_servers(self) -> List[Dict]:
        """Extract MCP server configurations.
        Returns list of dicts matching MCPServerDocument fields."""
        pass

    @abstractmethod
    def extract_memory(self) -> List[Dict]:
        """Extract memory/context entries.
        Returns list of dicts matching MemoryEntry fields."""
        pass
