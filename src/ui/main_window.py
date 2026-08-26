"""主窗口：地图 + 底边栏 + 接触列表 + EMCON 面板 + 频谱面板。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.demo import build_demo_environment

from .contact_list import ContactListWidget
from .emcon_panel import EmconPanel
from .map_widget import MapWidget
from .spectrum_widget import SpectrumWidget
from .unit_info_bar import UnitInfoBar


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("烧穿 BURNTHROUGH - 电子战海空兵推")
        self.resize(1280, 800)

        self.env = build_demo_environment()

        self.map_widget = MapWidget(self)
        self.map_widget.set_environment(self.env)
        self.map_widget.selection_changed.connect(self._on_selection_changed)
        self.map_widget.command_issued.connect(
            lambda msg: self.statusBar().showMessage(msg))

        self.unit_info_bar = UnitInfoBar(self)
        self.unit_info_bar.fire_clicked.connect(
            lambda: self.map_widget.set_attack_mode(True))
        self.unit_info_bar.radar_menu_requested.connect(self._on_radar_menu_requested)
        self.unit_info_bar.emcon_clicked.connect(
            lambda: self.emcon_panel.setVisible(not self.emcon_panel.isVisible()))

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.map_widget, 1)
        central_layout.addWidget(self.unit_info_bar)
        self.setCentralWidget(central)

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

        self.statusBar().showMessage("就绪 | 左键选中 | 右键菜单/航路点 | 中键平移")

        self._last_event_count = 0

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

        self.jammer_mode_action = QAction("干扰样式：瞄准", self)
        self.jammer_mode_action.triggered.connect(self._on_jammer_mode_clicked)
        toolbar.addAction(self.jammer_mode_action)

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
        self._update_unit_info_bar()
        if len(self.env.events) > self._last_event_count:
            self._last_event_count = len(self.env.events)
            msg = self.env.events[-1]["message"]
            self.statusBar().showMessage(f"[T+{self.env.time_s:.0f}s] {msg}")
        else:
            self.statusBar().showMessage(
                f"仿真时间 {self.env.time_s:.0f}s | 左键选中 | 右键菜单/航路点")

    def _on_pause_toggled(self, checked: bool) -> None:
        if checked:
            self.timer.stop()
            self.pause_action.setText("继续")
            self.statusBar().showMessage("已暂停")
        else:
            self.timer.start()
            self.pause_action.setText("暂停")
            self.statusBar().showMessage("运行中")

    # ------------------------------------------------------------------
    # 选择与底边栏
    # ------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        self._update_unit_info_bar()

    def _update_unit_info_bar(self) -> None:
        ids = self.map_widget.selected_platform_ids()
        contact = self.map_widget.selected_contact()
        if ids:
            self.unit_info_bar.show_platforms(self.env, ids)
        elif contact is not None:
            self.unit_info_bar.show_contact(self.env, contact[0], contact[1])
        else:
            self.unit_info_bar.show_platforms(self.env, [])

    def _on_radar_menu_requested(self) -> None:
        ids = self.map_widget.selected_platform_ids()
        if not ids:
            self.statusBar().showMessage("请先选中一个单位")
            return
        # 对选中的第一个有雷达的单位切换雷达
        for pid in ids:
            p = self.env.platforms.get(pid)
            if p and p.emitters:
                self._toggle_radars(p)
                break

    def _toggle_radars(self, platform) -> None:
        new_state = "off" if any(e.is_emitting for e in platform.emitters) else "on"
        for e in platform.emitters:
            e.emcon_state = new_state
        self.statusBar().showMessage(f"{platform.name}：雷达已{'关机' if new_state == 'off' else '开机'}")
        self.map_widget.refresh()

    def _on_emcon_changed(self) -> None:
        self.map_widget.refresh()
        self._sync_toolbar_actions()

    def _sync_toolbar_actions(self) -> None:
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

    def _on_jammer_mode_clicked(self) -> None:
        for jammer in self.env.all_jammers():
            new_mode = "barrage_noise" if jammer.current_mode == "spot_noise" else "spot_noise"
            jammer.set_mode(new_mode)
        mode = self.env.all_jammers()[0].current_mode if self.env.all_jammers() else "spot_noise"
        label = "干扰样式：阻塞" if mode == "barrage_noise" else "干扰样式：瞄准"
        self.jammer_mode_action.setText(label)
        self.map_widget.refresh()
        self.statusBar().showMessage(f"干扰样式已切换为 {'阻塞式' if mode == 'barrage_noise' else '瞄准式'}噪声")

    def _on_fit_view(self) -> None:
        self.map_widget.resetTransform()
        self.map_widget.centerOn(0, 0)
        self.statusBar().showMessage("视图已复位")

    def add_dock(self, area, dock: QDockWidget, widget):
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock
