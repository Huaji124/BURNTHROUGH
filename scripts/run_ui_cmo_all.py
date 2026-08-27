"""以完整 CMO 数据库（中国+世界）启动游戏。

用法：
    python scripts/run_ui_cmo_all.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

from data_loader.cmo_world_loader import load_cmo_world_environment
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.env = load_cmo_world_environment("data/cmo_all_full.json", side="blue")
    win.map_widget.set_environment(win.env)
    win.emcon_panel.populate(win.env)
    win.contact_list.update_contacts(win.env)
    win.spectrum_widget.set_environment(win.env)
    win.false_target_panel.update_false_targets(win.env)
    win._update_unit_info_bar()
    win.statusBar().showMessage(
        f"已加载完整 CMO 数据库：{len(win.env.platforms)} 个平台")
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
