from __future__ import annotations


class InterfaceSettingsMixin:
    """Persist and synchronize workspace layout, camera and view preferences."""

    def _set_option_checked(self, key: str, checked: bool) -> None:
        button = self._option_buttons.get(key)
        if button is not None:
            button.setChecked(bool(checked))

    def _settings_bool(self, key: str, default: bool) -> bool:
        return bool(self._settings.value(key, default, type=bool))

    def _restore_options(self) -> None:
        if self._settings.contains("interface/inspector_visible"):
            inspector_visible = self._settings_bool(
                "interface/inspector_visible",
                True,
            )
        else:
            inspector_visible = self._settings_bool(
                "interface/properties_panel_visible",
                True,
            )

        status_bar_visible = self._settings_bool(
            "interface/status_bar_visible",
            True,
        )
        view_controls_visible = self._settings_bool(
            "interface/view_controls_visible",
            True,
        )
        stock_visible = self._settings_bool("viewport/show_stock", True)
        grid_visible = self._settings_bool("viewport/show_grid", True)
        rulers_visible = self._settings_bool("viewport/show_rulers", True)
        reverse_horizontal = self._settings_bool(
            "viewport/reverse_horizontal_navigation",
            False,
        )
        invert_vertical = self._settings_bool(
            "viewport/invert_vertical_navigation",
            False,
        )

        self.properties_panel.setVisible(inspector_visible)
        self.inspector_button.setChecked(inspector_visible)
        if hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("inspector")
            if rail_button is not None:
                rail_button.setChecked(inspector_visible)
        self.statusBar().setVisible(status_bar_visible)
        self.viewport.set_view_controls_visible(view_controls_visible)
        self.viewport.show_stock = stock_visible
        self.viewport.show_grid = grid_visible
        self.viewport.set_rulers_visible(rulers_visible)
        self.viewport.set_reverse_horizontal_drag(reverse_horizontal)
        self.viewport.set_invert_vertical_drag(invert_vertical)

        orientation = str(
            self._settings.value(
                "viewport/transform_orientation",
                "global",
            )
        ).lower()
        if orientation not in {"global", "local"}:
            orientation = "global"
        snap_enabled = self._settings_bool(
            "viewport/transform_snap_enabled",
            False,
        )
        try:
            snap_step = float(
                self._settings.value(
                    "viewport/transform_snap_step_mm",
                    1.0,
                )
            )
        except (TypeError, ValueError):
            snap_step = 1.0
        snap_step = max(0.001, snap_step)

        self._set_transform_orientation(orientation)
        self.transform_snap_step_spin.setValue(snap_step)
        self.transform_snap_check.setChecked(snap_enabled)
        self._transform_snap_changed()

        stored_sizes = self._settings.value("interface/splitter_sizes")
        restored_splitter = False
        if isinstance(stored_sizes, list):
            try:
                sizes = [max(0, int(value)) for value in stored_sizes]
            except (TypeError, ValueError):
                sizes = []

            if len(sizes) == 2 and sum(sizes) > 0:
                self.workspace_splitter.setSizes(sizes)
                restored_splitter = True
            elif len(sizes) == 3 and sum(sizes) > 0:
                # Migrate the old Project | Canvas | Properties splitter.
                self.workspace_splitter.setSizes(
                    [sizes[0] + sizes[1], sizes[2]]
                )
                restored_splitter = True

        if not restored_splitter:
            self.workspace_splitter.setSizes(
                self._default_workspace_splitter_sizes()
            )

        projection = str(
            self._settings.value("viewport/projection_mode", "perspective")
        ).lower()
        view_name = str(self._settings.value("viewport/view_name", "Top"))
        standard_views = {"Top", "Bottom", "Front", "Back", "Left", "Right"}
        if view_name == "Isometric":
            self.viewport.set_isometric_view()
        elif view_name in standard_views:
            self.viewport.set_standard_view(
                view_name,
                projection_mode=(
                    "perspective"
                    if projection == "perspective"
                    else "orthographic"
                ),
            )
        elif projection == "perspective":
            self.viewport.set_perspective_view()
        else:
            self.viewport.set_orthographic_view()

        self._set_option_checked("properties_panel", inspector_visible)
        self._set_option_checked("status_bar", status_bar_visible)
        self._set_option_checked("view_controls", view_controls_visible)
        self._set_option_checked("stock", stock_visible)
        self._set_option_checked("grid", grid_visible)
        self._set_option_checked("rulers", rulers_visible)
        self._set_option_checked("reverse_horizontal", reverse_horizontal)
        self._set_option_checked("invert_vertical", invert_vertical)
        self.viewport.update()

    def _save_viewport_mode(self) -> None:
        self._settings.setValue(
            "viewport/projection_mode",
            self.viewport.projection_mode,
        )
        self._settings.setValue("viewport/view_name", self.viewport.view_name)

    def _save_interface_options(self) -> None:
        self._settings.setValue(
            "interface/inspector_visible",
            self.properties_panel.isVisible(),
        )
        self._settings.setValue(
            "interface/status_bar_visible",
            self.statusBar().isVisible(),
        )
        self._settings.setValue(
            "interface/view_controls_visible",
            self.viewport.view_controls_visible,
        )
        self._settings.setValue(
            "interface/splitter_sizes",
            self.workspace_splitter.sizes(),
        )
        self._settings.setValue("viewport/show_stock", self.viewport.show_stock)
        self._settings.setValue("viewport/show_grid", self.viewport.show_grid)
        self._settings.setValue("viewport/show_rulers", self.viewport.rulers_visible)
        self._settings.setValue(
            "viewport/reverse_horizontal_navigation",
            self.viewport.reverse_horizontal_drag,
        )
        self._settings.setValue(
            "viewport/invert_vertical_navigation",
            self.viewport.invert_vertical_drag,
        )
        self._settings.setValue(
            "viewport/transform_orientation",
            self.viewport.transform_orientation,
        )
        self._settings.setValue(
            "viewport/transform_snap_enabled",
            self.viewport.snap_enabled,
        )
        self._settings.setValue(
            "viewport/transform_snap_step_mm",
            self.viewport.snap_step_mm,
        )
        self._settings.remove("interface/project_panel_visible")
        self._settings.remove("interface/properties_panel_visible")
        self._settings.remove("viewport/reverse_horizontal_drag")
        self._save_viewport_mode()
        self._settings.sync()

    def _toggle_project_panel_option(self) -> None:
        """Compatibility alias: the former project pane is now the Layers popup."""

        self._show_layers_popup()

    def _toggle_properties_panel_option(self) -> None:
        visible = not self.properties_panel.isVisible()
        self.properties_panel.setVisible(visible)
        self.inspector_button.setChecked(visible)
        if hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("inspector")
            if rail_button is not None:
                rail_button.setChecked(visible)
        self._set_option_checked("properties_panel", visible)

        if visible:
            sizes = self.workspace_splitter.sizes()
            if len(sizes) == 2 and sizes[1] < 40:
                preferred = self._properties_panel_default_width()
                total = max(sum(sizes), preferred + 520)
                self.workspace_splitter.setSizes(
                    [max(520, total - preferred), preferred]
                )

        self._save_interface_options()

    def _toggle_status_bar_option(self) -> None:
        visible = not self.statusBar().isVisible()
        self.statusBar().setVisible(visible)
        self._set_option_checked("status_bar", visible)
        self._save_interface_options()

    def _toggle_view_controls_option(self) -> None:
        visible = not self.viewport.view_controls_visible
        self.viewport.set_view_controls_visible(visible)
        self._set_option_checked("view_controls", visible)
        self._save_interface_options()
        self.statusBar().showMessage(
            f"Viewport controls {'shown' if visible else 'hidden'}",
            2000,
        )

    def _toggle_reverse_horizontal_option(self) -> None:
        enabled = not self.viewport.reverse_horizontal_drag
        self.viewport.set_reverse_horizontal_drag(enabled)
        self._set_option_checked("reverse_horizontal", enabled)
        self._save_interface_options()
        state = "reversed" if enabled else "standard"
        self.statusBar().showMessage(
            f"Horizontal pan + orbit: {state}",
            2500,
        )

    def _toggle_invert_vertical_option(self) -> None:
        enabled = not self.viewport.invert_vertical_drag
        self.viewport.set_invert_vertical_drag(enabled)
        self._set_option_checked("invert_vertical", enabled)
        self._save_interface_options()
        state = "inverted" if enabled else "standard"
        self.statusBar().showMessage(
            f"Vertical pan + orbit: {state}",
            2500,
        )

    def _toggle_stock(self) -> None:
        self.viewport.toggle_stock()
        self._set_option_checked("stock", self.viewport.show_stock)
        self._save_interface_options()
        state = "shown" if self.viewport.show_stock else "hidden"
        self.statusBar().showMessage(f"Stock {state}", 2000)

    def _toggle_grid(self) -> None:
        self.viewport.toggle_grid()
        self._set_option_checked("grid", self.viewport.show_grid)
        self._save_interface_options()
        state = "shown" if self.viewport.show_grid else "hidden"
        self.statusBar().showMessage(f"Grid {state}", 2000)

    def _toggle_rulers(self) -> None:
        visible = not self.viewport.rulers_visible
        self.viewport.set_rulers_visible(visible)
        self._set_option_checked("rulers", visible)
        self._save_interface_options()
        state = "shown" if visible else "hidden"
        self.statusBar().showMessage(f"Viewport rulers {state}", 2000)

    def _set_perspective_option(self) -> None:
        self.viewport.set_perspective_view()
        self.statusBar().showMessage("Perspective projection", 2000)

    def _set_orthographic_option(self) -> None:
        self.viewport.set_orthographic_view()
        self.statusBar().showMessage("Orthographic projection", 2000)

    def _set_isometric_option(self) -> None:
        self.viewport.set_isometric_view()
        self.statusBar().showMessage("Isometric view", 2000)

    def _set_standard_view_option(self, name: str) -> None:
        self.viewport.set_standard_view(name)
        self.statusBar().showMessage(f"{name} view", 2000)

    def _reset_interface_options(self) -> None:
        self._settings.remove("interface")
        self._settings.remove("viewport")

        self.layers_popup.hide()
        self.properties_panel.show()
        self.inspector_button.setChecked(True)
        self.statusBar().show()
        self.workspace_splitter.setSizes(
            self._default_workspace_splitter_sizes()
        )

        self.viewport.set_view_controls_visible(True)
        self.viewport.show_stock = True
        self.viewport.show_grid = True
        self.viewport.set_rulers_visible(True)
        self.viewport.set_reverse_horizontal_drag(False)
        self.viewport.set_invert_vertical_drag(False)
        self.viewport.set_default_view()

        for key in (
            "properties_panel",
            "status_bar",
            "view_controls",
            "stock",
            "grid",
            "rulers",
        ):
            self._set_option_checked(key, True)
        self._set_option_checked("reverse_horizontal", False)
        self._set_option_checked("invert_vertical", False)

        self.viewport.update()
        self._save_interface_options()
        self.statusBar().showMessage("Workspace layout reset", 3000)
