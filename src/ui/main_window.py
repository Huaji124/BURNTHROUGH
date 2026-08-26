"""主窗口：地图 + 工具栏 + 接触列表 + EMCON 面板 + 频谱面板。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QDockWidget, QToolBar

from core.demo import build_demo_environment

from .map_widget import MapWidget
from .contact_list import ContactListWidget
from .spectrum_widget import SpectrumWidget
from .emcon_panel import EmconPanel


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("烧穿 BURNTHROUGH - 电子战海空兵推")
        self.resize(1280, 800)

        self.env = build_demo_environment()

        self.map_widget = MapWidget(self)
        self.map_widget.set_environment(self.env)
        self.setCentralWidget(self.map_widget)

        self._build_toolbar()

        self.contact_list = ContactListWidget(self)
        self.add_dock(Qt.DockWidgetArea.RightDockWidgetArea,
                      QDockWidget("接触列表", self), self.contact_list)

        self.emcon_panel = EmconPanel(self)
        self.add_dock(Qt.DockWidgetArea.LeftDockWidgetArea,
                      QDockWidget("EMCON 面板", self), self.emcon_panel)

        self.spectrum_widget = SpectrumWidget(self)
        self.add_dock(Qt.DockWidgetArea.BottomDockWidgetArea,
                      QDockWidget("频谱监视", self), self.spectrum_widget)

        self.statusBar().showMessage("就绪 | 滚轮缩放，左键拖拽平移")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.radar_action = QAction("雷达开机", self)
        self.radar_action.setCheckable(True)
        self.radar_action.setChecked(True)
        self.radar_action.setShortcut(QKeySequence("R"))
        self.radar_action.toggled.connect(self._on_radar_toggled)
        toolbar.addAction(self.radar_action)

        self.jammer_action = QAction("干扰机开机", self)
        self.jammer_action.setCheckable(True)
        self.jammer_action.setChecked(True)
        self.jammer_action.setShortcut(QKeySequence("J"))
        self.jammer_action.toggled.connect(self._on_jammer_toggled)
        toolbar.addAction(self.jammer_action)

        toolbar.addSeparator()
        fit_action = QAction("复位视图", self)
        fit_action.setShortcut(QKeySequence("F"))
        fit_action.triggered.connect(self._on_fit_view)
        toolbar.addAction(fit_action)

    def _on_radar_toggled(self, checked: bool) -> None:
        self.map_widget.set_radar_on(checked)
        self.radar_action.setText("雷达开机" if checked else "雷达关机")
        self.statusBar().showMessage(f"搜索雷达已{'开机' if checked else '关机'}")

    def _on_jammer_toggled(self, checked: bool) -> None:
        self.map_widget.set_jammer_on(checked)
        self.jammer_action.setText("干扰机开机" if checked else "干扰机关机")
        self.statusBar().showMessage(f"干扰机已{'开机' if checked else '关机'}")

    def _on_fit_view(self) -> None:
        self.map_widget.resetTransform()
        self.map_widget.centerOn(0, 0)
        self.statusBar().showMessage("视图已复位")

    def add_dock(self, area, dock: QDockWidget, widget):
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock
