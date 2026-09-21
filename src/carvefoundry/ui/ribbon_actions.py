"""Compatibility facade composing CarveFoundry's command action domains.

Command behavior is split by responsibility so feature work no longer grows a
single ribbon_actions.py monolith. Existing callers continue inheriting only
RibbonActionsMixin.
"""
from __future__ import annotations

from .cam_generation_dialog import CamGenerationDialogMixin
from .job_utility_actions import JobUtilityActionsMixin
from .project_edit_actions import ProjectEditActionsMixin
from .ribbon_action_state import RibbonActionStateMixin
from .ribbon_cam_actions import RibbonCamActionsMixin
from .ribbon_design_tools import RibbonDesignToolsMixin
from .ribbon_machine_actions import RibbonMachineActionsMixin
from .smart_value_actions import SmartValueActionsMixin
from .view_simulation_actions import ViewSimulationActionsMixin


class RibbonActionsMixin(
    RibbonActionStateMixin,
    ProjectEditActionsMixin,
    ViewSimulationActionsMixin,
    SmartValueActionsMixin,
    JobUtilityActionsMixin,
    RibbonDesignToolsMixin,
    RibbonCamActionsMixin,
    RibbonMachineActionsMixin,
    CamGenerationDialogMixin,
):
    """Compose application command implementations from focused domains."""
