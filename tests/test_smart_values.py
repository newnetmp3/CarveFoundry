import pytest

from carvefoundry.core.smart_values import SmartValueError, SmartValues


def test_named_values_can_reference_each_other() -> None:
    values = SmartValues.from_lines(
        """
        width = 120
        border = 6
        inside = width - 2 * border
        half = inside / 2
        """
    )

    assert values.resolve("inside") == pytest.approx(108.0)
    assert values.resolve("half") == pytest.approx(54.0)


def test_binding_expression_can_use_project_context() -> None:
    values = SmartValues.from_lines("margin = 12")

    result = values.evaluate(
        "stock_width / 2 - margin",
        extra_values={"stock_width": 300.0},
    )

    assert result == pytest.approx(138.0)


def test_cycles_are_rejected() -> None:
    with pytest.raises(SmartValueError, match="cycle"):
        SmartValues.from_lines(
            """
            a = b + 1
            b = a + 1
            """
        )


def test_arbitrary_python_execution_is_rejected() -> None:
    values = SmartValues()

    with pytest.raises(SmartValueError):
        values.evaluate("__import__('os').system('echo nope')")
