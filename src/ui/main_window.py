"""主窗口：地图 + 工具栏 + 接触列表 + EMCON 面板 + 频谱面板。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
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
        self.emcon_panel.populate(self.env)
        self.emcon_panel.state_changed.connect(self._on_emcon_changed)
        self.add_dock(Qt.DockWidgetArea.LeftDockWidgetArea,
                      QDockWidget("EMCON 面板", self), self.emcon_panel)

        self.spectrum_widget = SpectrumWidget(self)
        self.add_dock(Qt.DockWidgetArea.BottomDockWidgetArea,
                      QDockWidget("频谱监视", self), self.spectrum_widget)

        self.statusBar().showMessage("就绪 | 滚轮缩放，左键拖拽平移")

        # 模拟时钟：1 秒真实时间 = 1 秒仿真时间
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._sim_tick)
        self.timer.start()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.pause_action = QAction("暂停", self)
        self.pause_action.setCheckable(True)
        self.pause_action.setShortcut(QKeySequence("Space"))
        self.pause_action.toggled.connect(self._on_pause_toggled)
        toolbar.addAction(self.pause_action)

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

    # ------------------------------------------------------------------
    # 模拟循环
    # ------------------------------------------------------------------
    def _sim_tick(self) -> None:
        self.env.step(dt_s=1.0)
        self.map_widget.refresh()
        self.contact_list.update_contacts(self.env)
        self.statusBar().showMessage(
            f"仿真时间 {self.env.time_s:.0f}s | 滚轮缩放，左键拖拽平移")

    def _on_pause_toggled(self, checked: bool) -> None:
        if checked:
            self.timer.stop()
            self.pause_action.setText("继续")
            self.statusBar().showMessage("已暂停")
        else:
            self.timer.start()
            self.pause_action.setText("暂停")
            self.statusBar().showMessage("运行中")

    def _on_emcon_changed(self) -> None:
        self.map_widget.refresh()
        self._sync_toolbar_actions()

    def _sync_toolbar_actions(self) -> None:
        """EMCON 面板改动后同步工具栏按钮状态。"""
        for jammer in self.env.all_jammers():
            self.jammer_action.blockSignals(True)
            self.jammer_action.setChecked(jammer.is_jamming)
            self.jammer_action.blockSignals(False)
            break
        for emitter in self.env.all_emitters():
            self.radar_action.blockSignals(True)
            self.radar_action.setChecked(emitter.is_emitting)
            self.radar_action.blockSignals(False)
            break

    def _on_radar_toggled(self, checked: bool) -> None:
        for emitter in self.env.all_emitters():
            emitter.emcon_state = "on" if checked else "off"
        self.map_widget.refresh()
        self.radar_action.setText("雷达开机" if checked else "雷达关机")
        self.statusBar().showMessage(f"搜索雷达已{'开机' if checked else '关机'}")
        self.emcon_panel.populate(self.env)

    def _on_jammer_toggled(self, checked: bool) -> None:
        for jammer in self.env.all_jammers():
            jammer.emcon_state = "on" if checked else "off"
        self.map_widget.refresh()
        self.jammer_action.setText("干扰机开机" if checked else "干扰机关机")
        self.statusBar().showMessage(f"干扰机已{'开机' if checked else '关机'}")
        self.emcon_panel.populate(self.env)

    def _on_fit_view(self) -> None:
        self.map_widget.resetTransform()
        self.map_widget.centerOn(0, 0)
        self.statusBar().showMessage("视图已复位")

    def add_dock(self, area, dock: QDockWidget, widget):
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock
