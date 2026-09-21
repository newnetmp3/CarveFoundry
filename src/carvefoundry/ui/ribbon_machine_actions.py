"""Cutter library, GRBL machine and postprocessor actions."""
from __future__ import annotations

import json
from dataclasses import replace
from math import pi

from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.cam.gcode import GrblPostSettings
from carvefoundry.core.machine_profiles import MachineProfile, profiles_from_json, profiles_to_json
from carvefoundry.core.tools import DEFAULT_TOOLS, Cutter, ToolType

from .machine_control import MachineController

from .ribbon_forms import _ActionForm


class RibbonMachineActionsMixin:
    def _tool_to_dict(self, tool: Cutter) -> dict[str, object]:
        return {
            "name": tool.name,
            "tool_type": tool.tool_type.value,
            "diameter_mm": tool.diameter_mm,
            "angle_deg": tool.angle_deg,
            "tip_diameter_mm": tool.tip_diameter_mm,
            "taper_angle_deg": tool.taper_angle_deg,
            "ball_radius_mm": tool.ball_radius_mm,
            "profile_points": tool.profile_points,
        }

    def _tool_from_dict(self, value: object) -> Cutter | None:
        if not isinstance(value, dict):
            return None
        try:
            profile_raw = value.get("profile_points")
            profile = None
            if isinstance(profile_raw, list):
                profile = tuple(
                    (float(point[0]), float(point[1]))
                    for point in profile_raw
                )
            return Cutter(
                name=str(value["name"]),
                tool_type=ToolType(str(value["tool_type"])),
                diameter_mm=float(value["diameter_mm"]),
                angle_deg=(
                    None
                    if value.get("angle_deg") is None
                    else float(value["angle_deg"])
                ),
                tip_diameter_mm=float(value.get("tip_diameter_mm", 0.0)),
                taper_angle_deg=(
                    None
                    if value.get("taper_angle_deg") is None
                    else float(value["taper_angle_deg"])
                ),
                ball_radius_mm=(
                    None
                    if value.get("ball_radius_mm") is None
                    else float(value["ball_radius_mm"])
                ),
                profile_points=profile,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _load_custom_tools(self) -> list[Cutter]:
        raw = self._settings.value("tools/custom_json", "[]")
        try:
            payload = json.loads(str(raw))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        result: list[Cutter] = []
        for value in payload:
            tool = self._tool_from_dict(value)
            if tool is not None:
                result.append(tool)
        return result

    def _save_custom_tools(self) -> None:
        self._settings.setValue(
            "tools/custom_json",
            json.dumps([self._tool_to_dict(tool) for tool in self._custom_tools]),
        )
        self._settings.sync()

    def _all_tools(self) -> list[Cutter]:
        return [*DEFAULT_TOOLS, *self._custom_tools]

    def _reload_tool_combo(self, preferred_name: str | None = None) -> None:
        if not hasattr(self, "tool_combo"):
            return
        current = preferred_name
        if current is None:
            selected = self.tool_combo.currentData()
            current = selected.name if isinstance(selected, Cutter) else None
        self.tool_combo.clear()
        for tool in self._all_tools():
            self.tool_combo.addItem(tool.name, tool)
        if current:
            for index in range(self.tool_combo.count()):
                tool = self.tool_combo.itemData(index)
                if isinstance(tool, Cutter) and tool.name == current:
                    self.tool_combo.setCurrentIndex(index)
                    break

    def _show_tool_library(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Tool Library")
        dialog.resize(620, 380)
        layout = QHBoxLayout(dialog)
        tool_list = QListWidget()
        details = QLabel()
        details.setWordWrap(True)
        details.setMinimumWidth(300)
        layout.addWidget(tool_list, 1)
        layout.addWidget(details, 1)

        tools = self._all_tools()
        for tool in tools:
            tool_list.addItem(tool.name)

        def update_details(row: int) -> None:
            if not 0 <= row < len(tools):
                details.clear()
                return
            tool = tools[row]
            text = (
                f"{tool.name}\n\n"
                f"Type: {tool.tool_type.value.replace('_', ' ').title()}\n"
                f"Diameter: {tool.diameter_mm:g} mm"
            )
            if tool.angle_deg is not None:
                text += f"\nIncluded angle: {tool.angle_deg:g}°"
            if tool.tip_diameter_mm:
                text += f"\nTip diameter: {tool.tip_diameter_mm:g} mm"
            if tool.profile_points:
                text += "\n\nCustom profile:\n" + "\n".join(
                    f"r {radius:g} → h {height:g} mm"
                    for radius, height in tool.profile_points
                )
            details.setText(text)

        tool_list.currentRowChanged.connect(update_details)
        tool_list.setCurrentRow(0)
        dialog.exec()

    def _new_tool(self) -> None:
        form = _ActionForm(self, "New Tool")
        form.add_line("name", "Name", "Custom End Mill")
        type_names = [
            "Flat End Mill",
            "Ball Nose",
            "V-Bit",
            "Engraving Cone",
            "Tapered Ball Nose",
        ]
        form.add_combo("type", "Type", type_names, type_names[0])
        form.add_double("diameter", "Diameter", 3.175, minimum=0.01, suffix=" mm")
        form.add_double("angle", "Included angle", 60.0, minimum=1.0, maximum=179.0, suffix="°")
        form.add_double("tip", "Tip diameter", 0.0, minimum=0.0, suffix=" mm")
        form.add_double("taper", "Taper angle", 5.0, minimum=0.1, maximum=89.0, suffix="°")
        form.add_double("ball", "Ball radius", 1.0, minimum=0.01, suffix=" mm")
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        type_map = {
            "Flat End Mill": ToolType.FLAT_END_MILL,
            "Ball Nose": ToolType.BALL_NOSE,
            "V-Bit": ToolType.V_BIT,
            "Engraving Cone": ToolType.ENGRAVING_CONE,
            "Tapered Ball Nose": ToolType.TAPERED_BALL_NOSE,
        }
        tool_type = type_map[str(form.value("type"))]
        diameter = float(form.value("diameter"))
        kwargs: dict[str, object] = {}
        if tool_type in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}:
            kwargs["angle_deg"] = float(form.value("angle"))
            kwargs["tip_diameter_mm"] = float(form.value("tip"))
        elif tool_type is ToolType.TAPERED_BALL_NOSE:
            kwargs["ball_radius_mm"] = float(form.value("ball"))
            kwargs["taper_angle_deg"] = float(form.value("taper"))

        try:
            tool = Cutter(
                str(form.value("name")).strip() or "Custom Tool",
                tool_type,
                diameter,
                **kwargs,
            )
        except ValueError as exc:
            self.statusBar().showMessage(f"Tool invalid: {exc}", 5000)
            return
        self._custom_tools.append(tool)
        self._save_custom_tools()
        self._reload_tool_combo(tool.name)
        self.statusBar().showMessage(f"Added tool: {tool.name}", 3000)

    def _new_custom_profile_tool(self) -> None:
        form = _ActionForm(self, "Custom Cutter Profile")
        form.add_line("name", "Name", "Custom Profile")
        form.add_double("diameter", "Diameter", 6.0, minimum=0.01, suffix=" mm")
        form.add_line(
            "points",
            "Radius:height points",
            "0:0, 1:0.15, 3:1.5",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            points = tuple(
                (
                    float(pair.split(":", 1)[0].strip()),
                    float(pair.split(":", 1)[1].strip()),
                )
                for pair in str(form.value("points")).split(",")
            )
            tool = Cutter(
                str(form.value("name")).strip() or "Custom Profile",
                ToolType.CUSTOM,
                float(form.value("diameter")),
                profile_points=points,
            )
        except (IndexError, ValueError) as exc:
            self.statusBar().showMessage(f"Custom profile invalid: {exc}", 6000)
            return
        self._custom_tools.append(tool)
        self._save_custom_tools()
        self._reload_tool_combo(tool.name)
        self.statusBar().showMessage(f"Added custom profile: {tool.name}", 3000)

    def _feeds_speeds_calculator(self) -> None:
        cutter = self.tool_combo.currentData()
        if not isinstance(cutter, Cutter):
            return
        form = _ActionForm(self, "Feeds & Speeds Calculator")
        form.add_int("rpm", "Spindle RPM", 18000, minimum=100, maximum=100000)
        form.add_int("flutes", "Flutes", 2, minimum=1, maximum=12)
        form.add_double(
            "chipload",
            "Chip load / tooth",
            0.03,
            minimum=0.001,
            maximum=2.0,
            decimals=4,
            step=0.005,
            suffix=" mm",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        rpm = int(form.value("rpm"))
        flutes = int(form.value("flutes"))
        chipload = float(form.value("chipload"))
        feed = rpm * flutes * chipload
        surface_speed = pi * cutter.diameter_mm * rpm / 1000.0
        self._set_activity_info(
            f"Feeds & speeds estimate\n{cutter.name}\n\n"
            f"Feed: {feed:.0f} mm/min\n"
            f"Spindle: {rpm:,} RPM\n"
            f"Chip load: {chipload:g} mm/tooth\n"
            f"Surface speed: {surface_speed:.1f} m/min\n\n"
            "Verify against the cutter and material manufacturer's limits."
        )
        self.statusBar().showMessage(f"Calculated feed: {feed:.0f} mm/min", 5000)

    # ------------------------------------------------------------------
    # Machine
    # ------------------------------------------------------------------
    def _machine_profiles(self) -> tuple[list[MachineProfile], str]:
        raw = str(self._settings.value("machine/profiles_v1", ""))
        try:
            profiles, active_name = profiles_from_json(raw)
        except (TypeError, ValueError):
            profiles, active_name = [], None

        if not profiles:
            legacy = MachineProfile(
                name=str(
                    self._settings.value(
                        "machine/name",
                        "Onefinity / GRBL",
                    )
                ),
                port=str(self._settings.value("machine/port", "")),
                baud_rate=int(self._settings.value("machine/baud", 115200)),
                work_x_mm=float(
                    self._settings.value("machine/work_x_mm", 816.0)
                ),
                work_y_mm=float(
                    self._settings.value("machine/work_y_mm", 816.0)
                ),
                work_z_mm=float(
                    self._settings.value("machine/work_z_mm", 133.0)
                ),
            )
            profiles = [legacy]
            active_name = legacy.name

        names = {profile.name for profile in profiles}
        if active_name not in names:
            active_name = profiles[0].name
        return profiles, active_name

    def _save_machine_profiles(
        self,
        profiles: list[MachineProfile],
        active_name: str,
    ) -> None:
        if not profiles:
            raise ValueError("At least one machine profile is required.")
        names = {profile.name for profile in profiles}
        if active_name not in names:
            raise ValueError("Active machine profile is missing.")

        self._settings.setValue(
            "machine/profiles_v1",
            profiles_to_json(profiles, active_name=active_name),
        )
        active = next(
            profile for profile in profiles if profile.name == active_name
        )
        # Mirror the active profile into the older keys for compatibility with
        # existing installs and any external scripts reading these settings.
        self._settings.setValue("machine/name", active.name)
        self._settings.setValue("machine/port", active.port)
        self._settings.setValue("machine/baud", active.baud_rate)
        self._settings.setValue("machine/work_x_mm", active.work_x_mm)
        self._settings.setValue("machine/work_y_mm", active.work_y_mm)
        self._settings.setValue("machine/work_z_mm", active.work_z_mm)
        self._settings.sync()

    def _active_machine_profile(self) -> MachineProfile:
        profiles, active_name = self._machine_profiles()
        return next(
            profile for profile in profiles if profile.name == active_name
        )

    def _select_machine_profile(self) -> None:
        profiles, active_name = self._machine_profiles()
        names = [profile.name for profile in profiles]
        selected, accepted = QInputDialog.getItem(
            self,
            "Machine Profile",
            "Active machine",
            names,
            names.index(active_name),
            False,
        )
        if not accepted or not selected:
            return
        self._save_machine_profiles(profiles, str(selected))
        self.statusBar().showMessage(
            f"Active machine: {selected}",
            3000,
        )

    def _delete_machine_profile(self) -> None:
        profiles, active_name = self._machine_profiles()
        if len(profiles) <= 1:
            self.statusBar().showMessage(
                "Keep at least one machine profile",
                4000,
            )
            return
        names = [profile.name for profile in profiles]
        selected, accepted = QInputDialog.getItem(
            self,
            "Delete Machine Profile",
            "Profile",
            names,
            names.index(active_name),
            False,
        )
        if not accepted or not selected:
            return
        answer = QMessageBox.question(
            self,
            "Delete Machine Profile",
            f"Delete machine profile {selected!r}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        remaining = [
            profile for profile in profiles if profile.name != selected
        ]
        new_active = (
            active_name
            if active_name != selected
            else remaining[0].name
        )
        self._save_machine_profiles(remaining, new_active)
        self.statusBar().showMessage(
            f"Deleted machine profile: {selected}",
            3000,
        )

    def _machine_profile(self) -> None:
        profiles, active_name = self._machine_profiles()
        active = next(
            profile for profile in profiles if profile.name == active_name
        )
        ports = MachineController.available_ports()
        port_names = [name for name, _label in ports]
        choices = port_names or ([active.port] if active.port else [""])
        if active.port and active.port not in choices:
            choices.insert(0, active.port)

        form = _ActionForm(self, "Machine Profile")
        form.add_line("name", "Profile name", active.name)
        form.add_combo(
            "port",
            "Serial port",
            choices,
            active.port,
            editable=True,
        )
        form.add_int(
            "baud",
            "Baud rate",
            active.baud_rate,
            minimum=1200,
            maximum=2_000_000,
        )
        form.add_double(
            "work_x",
            "X travel",
            active.work_x_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "work_y",
            "Y travel",
            active.work_y_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "work_z",
            "Z travel",
            active.work_z_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_check(
            "parking",
            "Park after G-code",
            active.parking_enabled,
        )
        form.add_double(
            "park_x",
            "Park X",
            active.park_x_mm,
            minimum=-100000.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "park_y",
            "Park Y",
            active.park_y_mm,
            minimum=-100000.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "park_z",
            "Park Z clearance",
            active.park_z_mm,
            minimum=0.0,
            maximum=100000.0,
            suffix=" mm",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        edited = MachineProfile(
            name=str(form.value("name")).strip() or active.name,
            port=str(form.value("port")).strip(),
            baud_rate=int(form.value("baud")),
            work_x_mm=float(form.value("work_x")),
            work_y_mm=float(form.value("work_y")),
            work_z_mm=float(form.value("work_z")),
            parking_enabled=bool(form.value("parking")),
            park_x_mm=float(form.value("park_x")),
            park_y_mm=float(form.value("park_y")),
            park_z_mm=float(form.value("park_z")),
        )
        try:
            edited.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Machine Profile", str(exc))
            return

        # Renaming creates/replaces a named profile without losing the others.
        remaining = [
            profile
            for profile in profiles
            if profile.name not in {active.name, edited.name}
        ]
        remaining.append(edited)
        remaining.sort(key=lambda profile: profile.name.casefold())
        self._save_machine_profiles(remaining, edited.name)
        self.statusBar().showMessage(
            f"Machine profile saved: {edited.name}",
            3000,
        )

    def _machine_work_area(self) -> None:
        profile = self._active_machine_profile()
        form = _ActionForm(self, "Machine Work Area")
        form.add_double(
            "x",
            "X travel",
            profile.work_x_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "y",
            "Y travel",
            profile.work_y_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "z",
            "Z travel",
            profile.work_z_mm,
            minimum=1.0,
            suffix=" mm",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        profiles, active_name = self._machine_profiles()
        updated = MachineProfile(
            name=profile.name,
            port=profile.port,
            baud_rate=profile.baud_rate,
            work_x_mm=float(form.value("x")),
            work_y_mm=float(form.value("y")),
            work_z_mm=float(form.value("z")),
            parking_enabled=profile.parking_enabled,
            park_x_mm=profile.park_x_mm,
            park_y_mm=profile.park_y_mm,
            park_z_mm=profile.park_z_mm,
        )
        profiles = [
            updated if candidate.name == active_name else candidate
            for candidate in profiles
        ]
        self._save_machine_profiles(profiles, active_name)
        self.statusBar().showMessage("Machine work area saved", 3000)

    def _work_zero_mode(self) -> None:
        form = _ActionForm(self, "XY Work Zero")
        labels = ["Front Left Corner", "Center of Stock"]
        current = (
            "Center of Stock"
            if self.project.stock.xy_zero == "center"
            else "Front Left Corner"
        )
        form.add_combo("mode", "XY zero", labels, current)
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        mode = (
            "center"
            if form.value("mode") == "Center of Stock"
            else "bottom_left"
        )
        if mode == self.project.stock.xy_zero:
            return
        self._before_ribbon_mutation("change work zero")
        self.project.stock.xy_zero = mode
        self._after_ribbon_mutation("change work zero", True)
        self.viewport.update()
        self.statusBar().showMessage(
            "XY work zero set to "
            + ("stock center" if mode == "center" else "front-left corner"),
            3500,
        )

    def _machine_origin(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before setting origin",
                5000,
            )
            return
        form = _ActionForm(self, "Set Work Origin")
        form.add_check("x", "Set X = 0", True)
        form.add_check("y", "Set Y = 0", True)
        form.add_check("z", "Set Z = 0", False)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        axes = [
            axis
            for axis in ("X", "Y", "Z")
            if bool(form.value(axis.lower()))
        ]
        if not axes:
            return
        command = "G10 L20 P1 " + " ".join(f"{axis}0" for axis in axes)
        if self.machine_controller.send_line(command):
            self.statusBar().showMessage(
                f"Set work origin: {', '.join(axes)}",
                4000,
            )

    def _home_machine(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before homing",
                4000,
            )
            return
        if self.machine_controller.send_line("$H"):
            self.statusBar().showMessage("Machine homing started", 4000)

    def _go_to_work_zero(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before moving to work zero",
                4000,
            )
            return
        safe_z = float(self._settings.value("cam/safe_z_mm", 1.5))
        self.machine_controller.send_line("G90")
        self.machine_controller.send_line(f"G0 Z{safe_z:g}")
        self.machine_controller.send_line("G0 X0 Y0")
        self.statusBar().showMessage("Moving to XY work zero", 4000)

    def _park_machine(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before parking",
                4000,
            )
            return
        profile = self._active_machine_profile()
        clearance = max(
            profile.park_z_mm,
            float(self._settings.value("cam/safe_z_mm", 1.5)),
        )
        self.machine_controller.send_line("G90")
        self.machine_controller.send_line(f"G0 Z{clearance:g}")
        self.machine_controller.send_line(
            f"G0 X{profile.park_x_mm:g} Y{profile.park_y_mm:g}"
        )
        self.statusBar().showMessage(
            f"Parking {profile.name}",
            4000,
        )

    def _postprocessor_settings_dialog(self) -> None:
        form = _ActionForm(self, "Postprocessor")
        form.add_combo(
            "post",
            "Postprocessor",
            ["GRBL / Onefinity"],
            str(self._settings.value("post/name", "GRBL / Onefinity")),
        )
        form.add_int(
            "decimals",
            "Coordinate decimals",
            int(self._settings.value("post/decimals", 3)),
            minimum=0,
            maximum=6,
        )
        form.add_check(
            "comments",
            "Include comments",
            bool(self._settings.value("post/comments", True, type=bool)),
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings.setValue("post/name", form.value("post"))
        self._settings.setValue("post/decimals", int(form.value("decimals")))
        self._settings.setValue("post/comments", bool(form.value("comments")))
        self._settings.sync()
        self.statusBar().showMessage("Postprocessor settings saved", 3000)

    def _grbl_post_settings(self) -> GrblPostSettings:
        profile = self._active_machine_profile()
        center_zero = self.project.stock.xy_zero == "center"
        return GrblPostSettings(
            decimals=int(self._settings.value("post/decimals", 3)),
            include_comments=bool(
                self._settings.value("post/comments", True, type=bool)
            ),
            x_offset_mm=(
                -self.project.stock.width_mm / 2.0
                if center_zero
                else 0.0
            ),
            y_offset_mm=(
                -self.project.stock.height_mm / 2.0
                if center_zero
                else 0.0
            ),
            park_enabled=profile.parking_enabled,
            park_x_mm=profile.park_x_mm,
            park_y_mm=profile.park_y_mm,
            park_z_mm=profile.park_z_mm,
        )

    def _connect_machine(self) -> None:
        if self.machine_controller.connected:
            self.machine_controller.disconnect()
            return

        if self._machine_connect_button is not None:
            self._machine_connect_button.setChecked(False)

        profile = self._active_machine_profile()
        if not profile.port:
            self._machine_profile()
            profile = self._active_machine_profile()
        if not profile.port:
            self.statusBar().showMessage(
                "No serial port configured for the active machine",
                5000,
            )
            return
        self.statusBar().showMessage(
            f"Connecting {profile.name} on {profile.port}…"
        )
        if self.machine_controller.connect_serial(
            profile.port,
            profile.baud_rate,
        ):
            self.machine_controller.send_line("?")

    def _machine_connection_changed(self, connected: bool, port: str) -> None:
        if self._machine_connect_button is not None:
            self._machine_connect_button.setText(
                "Disconnect" if connected else "Connect"
            )
            self._machine_connect_button.setChecked(connected)

        if hasattr(self, "machine_status_label"):
            self.machine_status_label.setText(
                f"CONNECTED • {port}" if connected else "OFFLINE"
            )
            self.machine_status_label.setProperty(
                "connected",
                connected,
            )
            self.machine_status_label.style().unpolish(
                self.machine_status_label
            )
            self.machine_status_label.style().polish(
                self.machine_status_label
            )

        self.statusBar().showMessage(
            f"{'Connected to' if connected else 'Disconnected from'} {port}",
            4000,
        )

    def _machine_line_received(self, line: str) -> None:
        self.statusBar().showMessage(f"Machine: {line}", 3500)

    def _machine_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Machine: {message}", 6000)

    def _probe_machine(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage("Connect to the machine before probing", 5000)
            return
        form = _ActionForm(self, "Z Probe")
        form.add_double("distance", "Maximum downward travel", 15.0, minimum=0.1, suffix=" mm")
        form.add_double(
            "feed",
            "Probe feed",
            100.0,
            minimum=1.0,
            maximum=5000.0,
            suffix=" mm/min",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        answer = QMessageBox.question(
            self,
            "Start Z Probe",
            "The machine will move Z downward until the probe triggers.\n\n"
            "Confirm the probe is connected and positioned correctly.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        distance = float(form.value("distance"))
        feed = float(form.value("feed"))
        self.machine_controller.send_line(f"G38.2 Z-{distance:g} F{feed:g}")

    def _show_jog_controls(self) -> None:
        if self._jog_dialog is not None:
            self._jog_dialog.show()
            self._jog_dialog.raise_()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Jog")
        dialog.setModal(False)
        layout = QVBoxLayout(dialog)

        controls = QWidget()
        grid = QGridLayout(controls)
        step = QDoubleSpinBox()
        step.setRange(0.01, 100.0)
        step.setValue(1.0)
        step.setSuffix(" mm")
        feed = QDoubleSpinBox()
        feed.setRange(1.0, 10000.0)
        feed.setValue(1000.0)
        feed.setSuffix(" mm/min")
        grid.addWidget(QLabel("Step"), 0, 0)
        grid.addWidget(step, 0, 1)
        grid.addWidget(QLabel("Feed"), 1, 0)
        grid.addWidget(feed, 1, 1)

        def send(axis: str, sign: float) -> None:
            if not self.machine_controller.connected:
                self.statusBar().showMessage("Machine is not connected", 4000)
                return
            amount = step.value() * sign
            self.machine_controller.send_line(
                f"$J=G91 G21 {axis}{amount:g} F{feed.value():g}"
            )

        buttons = [
            ("Y+", "Y", 1.0, 2, 1),
            ("X-", "X", -1.0, 3, 0),
            ("X+", "X", 1.0, 3, 2),
            ("Y-", "Y", -1.0, 4, 1),
            ("Z+", "Z", 1.0, 2, 3),
            ("Z-", "Z", -1.0, 4, 3),
        ]
        for label, axis, sign, row, column in buttons:
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, a=axis, s=sign: send(a, s)
            )
            grid.addWidget(button, row, column)

        layout.addWidget(controls)
        dialog.finished.connect(lambda _result: setattr(self, "_jog_dialog", None))
        self._jog_dialog = dialog
        dialog.show()

    # ------------------------------------------------------------------
    # View / toolpath simulation
    # ------------------------------------------------------------------
