"""主窗口：地图 + 底边栏 + 接触列表 + EMCON 面板 + 频谱面板。"""

from __future__ import annotations

APP_VERSION = "f941d32"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.demo import build_demo_environment
from core.scenario import load_scenario, save_scenario
from data_loader.china_loader import load_china_environment
from data_loader.cmo_world_loader import (
    load_cmo_country_environment,
)

from .contact_list import ContactListWidget
from .emcon_panel import EmconPanel
from .false_target_panel import FalseTargetPanel
from .map_widget import MapWidget
from .signal_library_panel import SignalLibraryPanel
from .spectrum_widget import SpectrumWidget
from .unit_info_bar import UnitInfoBar
from .weapon_panel import WeaponPanel


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"烧穿 BURNTHROUGH - 电子战海空兵推 [{APP_VERSION}]")
        self.resize(1280, 800)

        self.env = build_demo_environment()
        try:
            self.env.load_signal_library("data/signal_params.json")
        except (OSError, ValueError, KeyError):
            pass

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
        self.weapon_panel = WeaponPanel(self)
        self.weapon_panel.weapon_selected.connect(self._on_weapon_selected)
        central_layout.addWidget(self.weapon_panel)
        central_layout.addWidget(self.unit_info_bar)
        self.setCentralWidget(central)

        self._build_toolbar()

        self.contact_list = ContactListWidget(self)
        self.contact_list.marked_changed.connect(self._on_contact_mark_changed)
        self.add_dock(Qt.DockWidgetArea.RightDockWidgetArea,
                      QDockWidget("接触列表", self), self.contact_list)

        self.emcon_panel = EmconPanel(self)
        self.emcon_panel.populate(self.env)
        self.emcon_panel.state_changed.connect(self._on_emcon_changed)
        self.add_dock(Qt.DockWidgetArea.LeftDockWidgetArea,
                      QDockWidget("EMCON 面板", self), self.emcon_panel)

        self.spectrum_widget = SpectrumWidget(self)
        self.spectrum_widget.set_environment(self.env)
        self.add_dock(Qt.DockWidgetArea.BottomDockWidgetArea,
                      QDockWidget("频谱监视", self), self.spectrum_widget)

        self.false_target_panel = FalseTargetPanel(self)
        self.false_target_panel.update_false_targets(self.env)
        self.add_dock(Qt.DockWidgetArea.RightDockWidgetArea,
                      QDockWidget("假目标列表", self), self.false_target_panel)

        self.signal_library_panel = SignalLibraryPanel(self)
        self.add_dock(Qt.DockWidgetArea.RightDockWidgetArea,
                      QDockWidget("信号参数库", self), self.signal_library_panel)

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
        toolbar.addWidget(QLabel(" 欺骗技术: "))
        self.deception_combo = QComboBox()
        self.deception_combo.addItems(["无", "RGPO", "VGPO", "假目标", "TWS增益"])
        self.deception_combo.setToolTip("选择蓝方干扰机的欺骗技术")
        self.deception_combo.currentTextChanged.connect(self._on_deception_changed)
        toolbar.addWidget(self.deception_combo)

        toolbar.addSeparator()
        fit_action = QAction("复位视图", self)
        fit_action.setShortcut(QKeySequence("F"))
        fit_action.triggered.connect(self._on_fit_view)
        toolbar.addAction(fit_action)

        toolbar.addSeparator()
        save_action = QAction("保存想定", self)
        save_action.triggered.connect(self._on_save_scenario)
        toolbar.addAction(save_action)
        load_action = QAction("加载想定", self)
        load_action.triggered.connect(self._on_load_scenario)
        toolbar.addAction(load_action)

        china_action = QAction("装载中国军力", self)
        china_action.triggered.connect(self._on_load_china)
        toolbar.addAction(china_action)

        cmo_action = QAction("装载CMO世界", self)
        cmo_action.triggered.connect(self._on_load_cmo_world)
        toolbar.addAction(cmo_action)

        cmo_all_action = QAction("装载完整CMO", self)
        cmo_all_action.triggered.connect(self._on_load_cmo_all)
        toolbar.addAction(cmo_all_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" 视角: "))
        self.side_combo = QComboBox()
        self.side_combo.addItems(["红方", "蓝方"])
        self.side_combo.setCurrentText("红方")
        self.side_combo.currentTextChanged.connect(self._on_side_changed)
        toolbar.addWidget(self.side_combo)

    # ------------------------------------------------------------------
    # 模拟循环
    # ------------------------------------------------------------------
    def _sim_tick(self) -> None:
        self.env.step(dt_s=1.0)
        if not getattr(self.env, 'waypoint_drag_lock', False):
            self.map_widget.refresh()
        self.contact_list.update_contacts(self.env)
        self.spectrum_widget.update()
        self.false_target_panel.update_false_targets(self.env)
        self._update_unit_info_bar()
        self.weapon_panel.show_platform(self.env, self._selected_platform_id())
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
    def _selected_platform_id(self) -> str | None:
        ids = self.map_widget.selected_platform_ids()
        return ids[0] if ids else None

    def _on_selection_changed(self) -> None:
        self._update_unit_info_bar()
        self.weapon_panel.show_platform(self.env, self._selected_platform_id())

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
        """按首个辐射源/干扰机的状态同步工具栏开关。"""
        jammer = next(iter(self.env.all_jammers()), None)
        if jammer is not None:
            self.jammer_action.blockSignals(True)
            self.jammer_action.setChecked(jammer.is_jamming)
            self.jammer_action.blockSignals(False)
        emitter = next(iter(self.env.all_emitters()), None)
        if emitter is not None:
            self.radar_action.blockSignals(True)
            self.radar_action.setChecked(emitter.is_emitting)
            self.radar_action.blockSignals(False)

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
        jammers = self.env.all_jammers()
        for jammer in jammers:
            new_mode = "barrage_noise" if jammer.current_mode == "spot_noise" else "spot_noise"
            jammer.set_mode(new_mode)
        mode = jammers[0].current_mode if jammers else "spot_noise"
        label = "干扰样式：阻塞" if mode == "barrage_noise" else "干扰样式：瞄准"
        self.jammer_mode_action.setText(label)
        self.map_widget.refresh()
        self.statusBar().showMessage(f"干扰样式已切换为 {'阻塞式' if mode == 'barrage_noise' else '瞄准式'}噪声")

    def _bind_environment(self, load_signal_library: bool = False) -> None:
        """切换 Environment 后统一刷新各面板。

        此前三个加载入口各自重复了 7 行刷新代码，且都没有重置
        _last_event_count：换到事件数更少的新想定后，状态栏会因为
        len(events) 一直追不上旧计数而彻底不再显示事件消息。
        """
        if load_signal_library:
            try:
                self.env.load_signal_library("data/signal_params.json")
            except (OSError, ValueError, KeyError):
                pass
        self.map_widget.set_environment(self.env)
        self.emcon_panel.populate(self.env)
        self.contact_list.update_contacts(self.env)
        self.spectrum_widget.set_environment(self.env)
        self.false_target_panel.update_false_targets(self.env)
        self._update_unit_info_bar()
        self.weapon_panel.show_platform(self.env, self._selected_platform_id())
        self._last_event_count = len(self.env.events)

    def _on_save_scenario(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存想定", "data/scenarios/demo_ew.json", "JSON (*.json)")
        if not path:
            return
        save_scenario(self.env, path)
        self.statusBar().showMessage(f"想定已保存：{path}")

    def _on_load_scenario(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载想定", "data/scenarios", "JSON (*.json)")
        if not path:
            return
        self.env = load_scenario(path)
        self._bind_environment(load_signal_library=True)
        self._on_side_changed(self.side_combo.currentText())
        self.statusBar().showMessage(f"想定已加载：{path}")

    def _on_deception_changed(self, text: str) -> None:
        technique = {
            "无": "none",
            "RGPO": "rgpo",
            "VGPO": "vgpo",
            "假目标": "false_target",
            "TWS增益": "tws_gain",
        }.get(text, "none")
        for jammer in self.env.all_jammers():
            jammer.set_technique(technique)
        self.map_widget.refresh()
        self.statusBar().showMessage(f"欺骗技术已切换：{text}")

    def _on_load_china(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载中国军力参考数据", "data", "JSON (*.json)")
        if not path:
            return
        try:
            self.env = load_china_environment(path, side="red")
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "加载失败", str(exc))
            return
        self._bind_environment()
        self.side_combo.setCurrentText("红方")
        self.statusBar().showMessage(f"已加载中国军力数据：{path}（{len(self.env.platforms)} 个平台）")

    def _on_load_cmo_world(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择 CMO 国家目录", "data/cmo_full_by_country")
        if not path:
            return
        try:
            self.env = load_cmo_country_environment(path, side="blue")
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "加载失败", str(exc))
            return
        self._bind_environment()
        self.side_combo.setCurrentText("蓝方")
        self.statusBar().showMessage(
            f"已加载 CMO 国家数据：{path}（{len(self.env.platforms)} 个平台）")

    def _on_load_cmo_all(self) -> None:
        QMessageBox.information(
            self, "说明",
            "完整 CMO 合并文件已移除（只保留 data/cmo_full_by_country）。\n"
            "请使用“装载CMO世界”选择一个国家目录加载。")

    def _on_weapon_selected(self, name: str) -> None:
        self.map_widget.set_selected_weapon(name)
        self.statusBar().showMessage(f"已选择武器：{name}")

    def _on_contact_mark_changed(self) -> None:
        self.contact_list.update_contacts(self.env)
        self.map_widget.refresh()
        self.statusBar().showMessage("接触人工标记已更新")

    def _on_side_changed(self, text: str) -> None:
        side = "red" if text == "红方" else "blue"
        self.map_widget.set_player_side(side)
        self.contact_list.set_player_side(side)
        self.emcon_panel.set_player_side(side)
        self.emcon_panel.populate(self.env)
        self.false_target_panel.set_player_side(side)
        self.false_target_panel.update_false_targets(self.env)
        self.spectrum_widget.set_player_side(side)
        self._update_unit_info_bar()
        self.weapon_panel.show_platform(self.env, self._selected_platform_id())
        self.statusBar().showMessage(f"当前视角：{text}（仅显示己方/己方传感器接触）")

    def _on_fit_view(self) -> None:
        self.map_widget.fit_to_world()
        self.statusBar().showMessage("视图已复位")

    def add_dock(self, area, dock: QDockWidget, widget):
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock
