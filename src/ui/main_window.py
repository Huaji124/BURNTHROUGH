"""主窗口：地图 + 接触列表 + EMCON 面板 + 频谱面板。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QDockWidget

from .map_widget import MapWidget
from .contact_list import ContactListWidget
from .spectrum_widget import SpectrumWidget
from .emcon_panel import EmconPanel


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("电子战海空兵推原型 - EW Wargame Prototype")
        self.resize(1280, 800)

        self.map_widget = MapWidget(self)
        self.setCentralWidget(self.map_widget)

        self.contact_list = ContactListWidget(self)
        self.add_dock(Qt.DockWidgetArea.RightDockWidgetArea,
                      QDockWidget("接触列表", self), self.contact_list)

        self.emcon_panel = EmconPanel(self)
        self.add_dock(Qt.DockWidgetArea.LeftDockWidgetArea,
                      QDockWidget("EMCON 面板", self), self.emcon_panel)

        self.spectrum_widget = SpectrumWidget(self)
        self.add_dock(Qt.DockWidgetArea.BottomDockWidgetArea,
                      QDockWidget("频谱监视", self), self.spectrum_widget)

    def add_dock(self, area, dock: QDockWidget, widget):
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock
