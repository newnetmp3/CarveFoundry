"""Compatibility facade for workspace command/UI builders.

The implementation is split by responsibility:
- workspace_action_registry.py owns canonical QActions;
- workspace_menu_builder.py owns the desktop dropdown menus;
- workspace_surface_builder.py owns the hidden ribbon compatibility controls
  and visible vertical tool rail.

Keeping this facade preserves the existing MainWindow inheritance API.
"""
from __future__ import annotations

from .workspace_action_registry import WorkspaceActionRegistryMixin
from .workspace_menu_builder import WorkspaceMenuBuilderMixin
from .workspace_surface_builder import WorkspaceSurfaceBuilderMixin


class WorkspaceCommandsMixin(
    WorkspaceActionRegistryMixin,
    WorkspaceMenuBuilderMixin,
    WorkspaceSurfaceBuilderMixin,
):
    """Compose the workspace command surfaces without owning implementation."""
