from __future__ import annotations

from PySide6.QtCore import QIODevice, QObject, Signal

try:
    from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo
except ImportError:  # pragma: no cover - depends on Qt packaging
    QSerialPort = None  # type: ignore[assignment]
    QSerialPortInfo = None  # type: ignore[assignment]


class MachineController(QObject):
    """Small GRBL-family serial transport used by the Machine ribbon.

    The controller intentionally sends nothing until the user explicitly invokes
    a machine action.  Connection state and received controller text are exposed
    as Qt signals so the UI can remain responsive.
    """

    connectionChanged = Signal(bool, str)
    lineReceived = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial = QSerialPort(self) if QSerialPort is not None else None
        self._rx_buffer = bytearray()
        if self._serial is not None:
            self._serial.readyRead.connect(self._read_ready)
            self._serial.errorOccurred.connect(self._serial_error)

    @property
    def available(self) -> bool:
        return self._serial is not None and QSerialPortInfo is not None

    @property
    def connected(self) -> bool:
        return bool(self._serial is not None and self._serial.isOpen())

    @property
    def port_name(self) -> str:
        if self._serial is None:
            return ""
        return self._serial.portName()

    @staticmethod
    def available_ports() -> list[tuple[str, str]]:
        if QSerialPortInfo is None:
            return []
        result: list[tuple[str, str]] = []
        for info in QSerialPortInfo.availablePorts():
            description = info.description().strip()
            label = info.portName()
            if description:
                label += f" — {description}"
            result.append((info.portName(), label))
        return result

    def connect_serial(self, port_name: str, baud_rate: int = 115200) -> bool:
        if self._serial is None:
            self.errorOccurred.emit("Qt SerialPort support is not available.")
            return False
        if self._serial.isOpen():
            self._serial.close()

        self._serial.setPortName(port_name)
        self._serial.setBaudRate(int(baud_rate))
        self._serial.setDataBits(QSerialPort.DataBits.Data8)
        self._serial.setParity(QSerialPort.Parity.NoParity)
        self._serial.setStopBits(QSerialPort.StopBits.OneStop)
        self._serial.setFlowControl(QSerialPort.FlowControl.NoFlowControl)

        if not self._serial.open(QIODevice.OpenModeFlag.ReadWrite):
            self.errorOccurred.emit(
                self._serial.errorString() or f"Could not open {port_name}."
            )
            return False

        self._rx_buffer.clear()
        self.connectionChanged.emit(True, port_name)
        return True

    def disconnect(self) -> None:
        if self._serial is not None and self._serial.isOpen():
            name = self._serial.portName()
            self._serial.close()
            self.connectionChanged.emit(False, name)

    def send_line(self, command: str) -> bool:
        if self._serial is None or not self._serial.isOpen():
            self.errorOccurred.emit("No machine is connected.")
            return False
        line = command.strip()
        if not line:
            return False
        payload = (line + "\n").encode("ascii", errors="strict")
        written = self._serial.write(payload)
        if written < 0:
            self.errorOccurred.emit(self._serial.errorString() or "Serial write failed.")
            return False
        self._serial.flush()
        return True

    def _read_ready(self) -> None:
        if self._serial is None:
            return
        self._rx_buffer.extend(bytes(self._serial.readAll()))
        while b"\n" in self._rx_buffer:
            raw, _, remainder = self._rx_buffer.partition(b"\n")
            self._rx_buffer = bytearray(remainder)
            text = raw.rstrip(b"\r").decode("utf-8", errors="replace").strip()
            if text:
                self.lineReceived.emit(text)

    def _serial_error(self, error) -> None:
        if self._serial is None or QSerialPort is None:
            return
        if error == QSerialPort.SerialPortError.NoError:
            return
        if self._serial.isOpen():
            self.errorOccurred.emit(self._serial.errorString())
