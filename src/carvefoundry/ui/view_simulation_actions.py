"""Viewport presentation and lightweight toolpath playback actions."""
from __future__ import annotations


class ViewSimulationActionsMixin:
    """Own 2D view, path visibility, and preview playback controls."""

    def _set_2d_view(self) -> None:
        self.viewport.set_standard_view("Top", projection_mode="orthographic")
        self.statusBar().showMessage("2D top view", 2500)

    def _toggle_toolpaths_view(self) -> None:
        visible = not self.viewport.toolpaths_visible
        self.viewport.set_toolpaths_visible(visible)
        if self._toolpaths_view_button is not None:
            self._toolpaths_view_button.setChecked(visible)
        self.statusBar().showMessage(
            f"Toolpaths {'shown' if visible else 'hidden'}",
            2500,
        )

    def _toggle_rapids_view(self) -> None:
        visible = not self.viewport.rapids_visible
        self.viewport.set_rapids_visible(visible)
        if self._rapids_view_button is not None:
            self._rapids_view_button.setChecked(visible)
        self.statusBar().showMessage(
            f"Rapids {'shown' if visible else 'hidden'}",
            2500,
        )

    def _simulate_toolpaths(self) -> None:
        if not self.project.toolpaths:
            self.statusBar().showMessage("No calculated toolpaths to simulate", 4000)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            return

        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
            self.viewport.set_simulation_fraction(1.0)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            self.statusBar().showMessage("Simulation stopped", 2500)
            return

        self.viewport.set_toolpaths_visible(True)
        self.viewport.set_simulation_fraction(0.0)
        if self._toolpaths_view_button is not None:
            self._toolpaths_view_button.setChecked(True)
        if self._simulation_button is not None:
            self._simulation_button.setChecked(True)
        self._simulation_timer.start()
        self.statusBar().showMessage("Toolpath simulation running…")

    def _advance_simulation(self) -> None:
        total_segments = sum(
            max(0, len(toolpath.moves) - 1)
            for toolpath in self.project.toolpaths
        )
        increment = max(0.005, 1.0 / max(total_segments, 1))
        fraction = self.viewport.simulation_fraction + increment
        if fraction >= 1.0:
            self._simulation_timer.stop()
            self.viewport.set_simulation_fraction(1.0)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            self.statusBar().showMessage("Simulation complete", 3000)
            return
        self.viewport.set_simulation_fraction(fraction)
        self.statusBar().showMessage(
            f"Simulating toolpath… {fraction * 100:.0f}%"
        )


