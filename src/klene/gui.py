from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from klene.cleaner import (
    clean_aur_cache,
    clean_flatpak_unused,
    clean_journal,
    clean_orphans,
    clean_pacman_cache,
    clean_thumbnails,
    clean_trash,
    clean_user_cache,
)
from klene.logging_config import configure_logging
from klene.models import CleanupResult, CleanupTarget
from klene.scanner import scan_system
from klene.utils import format_bytes


CARD_ORDER = [
    "pacman-cache",
    "orphans",
    "journal",
    "user-cache",
    "trash",
    "thumbnails",
    "aur-cache",
    "flatpak-cache",
]


@dataclass(slots=True)
class WorkerRequest:
    action: str
    callback: Callable[[], object]


class Worker(QObject):
    finished = Signal(str, object)
    failed = Signal(str)

    def __init__(self, request: WorkerRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        try:
            result = self.request.callback()
        except Exception as exc:  # pragma: no cover
            self.failed.emit(str(exc))
            return
        self.finished.emit(self.request.action, result)


class TargetCard(QFrame):
    def __init__(self, target: CleanupTarget) -> None:
        super().__init__()
        self.target_key = target.key
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        self.checkbox = QCheckBox(target.title)
        self.checkbox.setChecked(target.selected_by_default and target.available)
        self.checkbox.setEnabled(target.available and target.cleanup_supported)
        self.status_label = QLabel(target.status.value.title())
        self.status_label.setObjectName("badge")
        self.size_label = QLabel(format_bytes(target.estimated_bytes))
        self.details_label = QLabel(target.details)
        self.details_label.setWordWrap(True)

        top = QHBoxLayout()
        top.addWidget(self.checkbox)
        top.addStretch(1)
        top.addWidget(self.status_label)

        layout.addLayout(top)
        layout.addWidget(QLabel(target.description))
        layout.addWidget(self.size_label)
        layout.addWidget(self.details_label)

    def update_target(self, target: CleanupTarget) -> None:
        self.checkbox.setEnabled(target.available and target.cleanup_supported)
        if self.checkbox.isEnabled() and not self.checkbox.isChecked():
            pass
        elif not self.checkbox.isEnabled():
            self.checkbox.setChecked(False)
        self.status_label.setText(target.status.value.title())
        self.size_label.setText(format_bytes(target.estimated_bytes))
        self.details_label.setText(target.details)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Klene")
        self.resize(980, 700)
        self.cards: dict[str, TargetCard] = {}
        self.latest_targets: dict[str, CleanupTarget] = {}
        self.log_path = configure_logging()
        self._thread: QThread | None = None
        self._worker: Worker | None = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel("Klene")
        title.setObjectName("title")
        subtitle = QLabel("Simple cleanup for Arch Linux")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_host = QWidget()
        self.grid = QGridLayout(scroll_host)
        self.grid.setSpacing(14)
        scroll.setWidget(scroll_host)
        layout.addWidget(scroll, stretch=1)

        button_row = QHBoxLayout()
        self.scan_button = QPushButton("Scan")
        self.preview_button = QPushButton("Preview Cleanup")
        self.clean_button = QPushButton("Clean Selected")
        self.logs_button = QPushButton("Open Logs")
        self.about_button = QPushButton("About")
        for button in [
            self.scan_button,
            self.preview_button,
            self.clean_button,
            self.logs_button,
            self.about_button,
        ]:
            button_row.addWidget(button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready")
        status_row = QHBoxLayout()
        status_row.addWidget(self.progress, stretch=1)
        status_row.addWidget(self.status_label)
        layout.addLayout(status_row)

        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("monospace"))
        self.log_output.setMinimumHeight(180)
        log_layout.addWidget(self.log_output)
        layout.addWidget(log_group)

        self.setCentralWidget(central)
        self._apply_styles()
        self._wire_actions()
        self._build_menu()
        self.start_scan()

    def _build_menu(self) -> None:
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(about_action)

    def _wire_actions(self) -> None:
        self.scan_button.clicked.connect(self.start_scan)
        self.preview_button.clicked.connect(self.preview_cleanup)
        self.clean_button.clicked.connect(self.clean_selected)
        self.logs_button.clicked.connect(self.open_logs)
        self.about_button.clicked.connect(self.show_about)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #11161d;
                color: #e7ecf2;
            }
            QLabel#title {
                font-size: 28px;
                font-weight: 700;
            }
            QLabel#subtitle {
                color: #90a0b5;
                font-size: 14px;
            }
            QFrame#card {
                background: #171d26;
                border: 1px solid #283141;
                border-radius: 14px;
                padding: 12px;
            }
            QLabel#badge {
                background: #243244;
                border-radius: 10px;
                padding: 4px 10px;
                color: #b9d6ff;
            }
            QPushButton {
                background: #233247;
                border: 1px solid #31445f;
                border-radius: 10px;
                padding: 10px 14px;
            }
            QPushButton:hover {
                background: #2d405b;
            }
            QPlainTextEdit, QGroupBox {
                background: #0c1117;
                border: 1px solid #283141;
                border-radius: 12px;
            }
            QProgressBar {
                background: #0c1117;
                border: 1px solid #283141;
                border-radius: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #5fa8ff;
                border-radius: 8px;
            }
            """
        )

    def append_log(self, line: str) -> None:
        self.log_output.appendPlainText(line)

    def set_busy(self, busy: bool, message: str) -> None:
        self.progress.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress.setValue(0)
        self.status_label.setText(message)
        for button in [self.scan_button, self.preview_button, self.clean_button]:
            button.setEnabled(not busy)

    def _run_worker(self, action: str, callback: Callable[[], object]) -> None:
        self.set_busy(True, f"{action} in progress")
        request = WorkerRequest(action=action, callback=callback)
        self._thread = QThread(self)
        self._worker = Worker(request)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._handle_worker_result)
        self._worker.failed.connect(self._handle_worker_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self._thread.start()

    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None

    def _handle_worker_error(self, message: str) -> None:
        self.set_busy(False, "Error")
        self.append_log(f"ERROR: {message}")
        QMessageBox.critical(self, "Klene", message)

    def _handle_worker_result(self, action: str, payload: object) -> None:
        self.set_busy(False, f"{action} finished")
        if action == "Scan":
            self.populate_cards(payload)
            self.append_log("Scan completed.")
        elif action == "Preview":
            self._show_preview(payload)
        elif action == "Clean":
            self._show_cleanup_results(payload)

    def populate_cards(self, report: object) -> None:
        targets = getattr(report, "targets", [])
        self.latest_targets = {target.key: target for target in targets}
        for index, key in enumerate(CARD_ORDER):
            if key not in self.latest_targets:
                continue
            row, col = divmod(index, 2)
            target = self.latest_targets[key]
            if key not in self.cards:
                card = TargetCard(target)
                self.cards[key] = card
                self.grid.addWidget(card, row, col)
            else:
                self.cards[key].update_target(target)

    def selected_keys(self) -> list[str]:
        return [key for key, card in self.cards.items() if card.checkbox.isChecked()]

    def start_scan(self) -> None:
        self.append_log("Running scan...")
        self._run_worker("Scan", scan_system)

    def preview_cleanup(self) -> None:
        keys = self.selected_keys()
        preview_lines = []
        for key in keys:
            target = self.latest_targets.get(key)
            if not target:
                continue
            preview_lines.append(f"{target.title}: {format_bytes(target.estimated_bytes)}")
            preview_lines.extend(f"  {line}" for line in target.preview[:10])
        self._run_worker("Preview", lambda: preview_lines)

    def _show_preview(self, lines: object) -> None:
        preview = "\n".join(lines if isinstance(lines, list) else [])
        if not preview:
            preview = "No cleanup targets selected."
        self.append_log(preview)
        QMessageBox.information(self, "Preview Cleanup", preview)

    def clean_selected(self) -> None:
        keys = self.selected_keys()
        if not keys:
            QMessageBox.information(self, "Klene", "Select at least one cleanup target.")
            return
        if "orphans" in keys:
            warning = "Orphan package removal affects installed packages. Continue?"
            if QMessageBox.warning(self, "Klene", warning, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            warning = "Confirm orphan package removal again before cleanup runs."
            if QMessageBox.warning(self, "Klene", warning, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        confirm = QMessageBox.question(
            self,
            "Klene",
            "Run cleanup for the selected targets?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._run_worker("Clean", lambda: self._perform_selected_cleanup(keys))

    def _perform_selected_cleanup(self, keys: list[str]) -> list[CleanupResult]:
        handlers = {
            "pacman-cache": lambda: clean_pacman_cache(dry_run=False),
            "orphans": lambda: clean_orphans(dry_run=False),
            "journal": lambda: clean_journal(dry_run=False),
            "user-cache": lambda: clean_user_cache(dry_run=False),
            "trash": lambda: clean_trash(dry_run=False),
            "thumbnails": lambda: clean_thumbnails(dry_run=False),
            "aur-cache": lambda: clean_aur_cache(dry_run=False),
            "flatpak-cache": lambda: clean_flatpak_unused(dry_run=False),
        }
        return [handlers[key]() for key in keys if key in handlers]

    def _show_cleanup_results(self, results: object) -> None:
        lines = []
        for result in results if isinstance(results, list) else []:
            lines.append(f"{result.key}: {result.message}")
        self.append_log("\n".join(lines))
        QMessageBox.information(self, "Cleanup Results", "\n".join(lines) or "No results.")
        self.start_scan()

    def open_logs(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path)))

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "About Klene",
            "Klene\n\nSafe cleanup utility for Arch Linux.\nScans first, previews changes, and requires confirmation before cleanup.",
        )


def launch_gui() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
