"""Compatibility facade for design selection and transform controllers."""
from __future__ import annotations

from .object_lifecycle_actions import ObjectLifecycleActionsMixin
from .selection_controller import SelectionControllerMixin
from .transform_interaction_controller import TransformInteractionControllerMixin


class SelectionTransformControllerMixin(
    SelectionControllerMixin,
    TransformInteractionControllerMixin,
    ObjectLifecycleActionsMixin,
):
    """Compose selection, transform, and selected-object lifecycle behavior."""
