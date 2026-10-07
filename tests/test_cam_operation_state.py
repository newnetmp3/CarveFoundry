from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.ui.toolpath_state_controller import ToolpathStateControllerMixin


class _Timer:
    def isActive(self) -> bool:
        return False

    def stop(self) -> None:
        pass


class _Viewport:
    toolpaths_visible = False
    rapids_visible = False

    def __init__(self) -> None:
        self.visible = False
        self.simulation_fraction = 1.0

    def set_simulation_fraction(self, value: float) -> None:
        self.simulation_fraction = value

    def set_toolpaths_visible(self, visible: bool) -> None:
        self.visible = visible

    def update(self) -> None:
        pass


class _Host(ToolpathStateControllerMixin):
    def __init__(self, project: Project) -> None:
        self.project = project
        self._toolpath_output_buttons = []
        self._toolpaths_view_button = None
        self._rapids_view_button = None
        self._simulation_button = None
        self._recalculate_button = None
        self._simulation_timer = _Timer()
        self._toolpath_preview_window = None
        self._prepared_toolpath_geometry = object()
        self._prepared_toolpath_stats = object()
        self._toolpaths_stale_reason = None
        self.viewport = _Viewport()
        self.activity = ""

    def _set_activity_info(self, text: str) -> None:
        self.activity = text


def _cutter() -> Cutter:
    return Cutter("6 mm flat", ToolType.FLAT_END_MILL, 6.0)


def _path(name: str, operation_id: str, source_item_id: str) -> Toolpath:
    return Toolpath(
        name=name,
        operation="profile",
        cutter=_cutter(),
        safe_z_mm=1.5,
        source_item_id=source_item_id,
        cam_operation_id=operation_id,
    )


def test_invalidation_keeps_earlier_independent_stage() -> None:
    first = ProjectItem("First")
    second = ProjectItem("Second")
    first_operation = CamOperation(
        "profile",
        _cutter(),
        source_item_ids=(first.item_id,),
    )
    second_operation = CamOperation(
        "profile",
        _cutter(),
        source_item_ids=(second.item_id,),
    )
    project = Project(
        items=[first, second],
        cam_operations=[first_operation, second_operation],
        toolpaths=[
            _path("First profile", first_operation.operation_id, first.item_id),
            _path("Second profile", second_operation.operation_id, second.item_id),
        ],
    )
    host = _Host(project)

    assert host._invalidate_toolpaths(
        "Model transform",
        source_item_ids={second.item_id},
    )

    assert not first_operation.needs_recalculation
    assert second_operation.needs_recalculation
    assert [path.name for path in project.toolpaths] == ["First profile"]
    assert "retained" in host.activity


def test_invalidation_marks_downstream_stages_stale() -> None:
    first = ProjectItem("First")
    second = ProjectItem("Second")
    first_operation = CamOperation(
        "profile",
        _cutter(),
        source_item_ids=(first.item_id,),
    )
    second_operation = CamOperation(
        "profile",
        _cutter(),
        source_item_ids=(second.item_id,),
    )
    project = Project(
        items=[first, second],
        cam_operations=[first_operation, second_operation],
        toolpaths=[
            _path("First profile", first_operation.operation_id, first.item_id),
            _path("Second profile", second_operation.operation_id, second.item_id),
        ],
    )
    host = _Host(project)

    host._invalidate_toolpaths(
        "Model transform",
        source_item_ids={first.item_id},
    )

    assert first_operation.needs_recalculation
    assert second_operation.needs_recalculation
    assert project.toolpaths == []
