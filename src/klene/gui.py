from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QSize, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
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
    QSizePolicy,
    QSplashScreen,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from klene import __version__
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
from klene.metadata import (
    APP_DESCRIPTION,
    APP_NAME,
    APP_SUMMARY,
    APP_TAGLINE,
    AUTHOR_CREDIT,
    AUTHOR_NAME,
    AUTHOR_WEBSITE,
    packaged_logo_path,
)
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

APP_TITLE = APP_NAME
APP_SUBTITLE = APP_TAGLINE
APP_HERO_SUMMARY = APP_DESCRIPTION
SPLASH_MIN_MS = 900


def app_logo_path() -> Path:
    return packaged_logo_path()


def load_logo_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(str(app_logo_path()))
    if pixmap.isNull():
        return QPixmap()
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def load_app_icon() -> QIcon:
    return QIcon(str(app_logo_path()))


def build_message_box(
    parent: QWidget | None,
    *,
    title: str,
    icon: QMessageBox.Icon,
    text: str,
    informative: str | None = None,
    detailed: str | None = None,
    buttons: QMessageBox.StandardButtons = QMessageBox.Ok,
    default_button: QMessageBox.StandardButton | None = None,
) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(icon)
    box.setText(text)
    if informative:
        box.setInformativeText(informative)
    if detailed:
        box.setDetailedText(detailed)
    box.setStandardButtons(buttons)
    if default_button is not None:
        box.setDefaultButton(default_button)
    return box


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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(target.selected_by_default and target.available)
        self.checkbox.setEnabled(target.available and target.cleanup_supported)
        self.checkbox.toggled.connect(self._refresh_selection_state)

        self.title_label = QLabel(target.title)
        self.title_label.setObjectName("cardTitle")
        self.description_label = QLabel(target.description)
        self.description_label.setObjectName("cardDescription")
        self.description_label.setWordWrap(True)

        self.status_label = QLabel()
        self.status_label.setObjectName("badge")

        self.estimated_label = QLabel()
        self.estimated_label.setObjectName("metricValue")
        self.state_label = QLabel()
        self.state_label.setObjectName("selectionState")
        self.details_label = QLabel()
        self.details_label.setObjectName("cardNote")
        self.details_label.setWordWrap(True)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.checkbox, alignment=Qt.AlignTop)
        heading_layout = QVBoxLayout()
        heading_layout.setSpacing(4)
        heading_layout.addWidget(self.title_label)
        heading_layout.addWidget(self.description_label)
        top.addLayout(heading_layout, stretch=1)
        top.addWidget(self.status_label, alignment=Qt.AlignTop)

        metrics = QHBoxLayout()
        metrics.setSpacing(24)
        estimated_group = QVBoxLayout()
        estimated_group.setSpacing(2)
        estimated_caption = QLabel("Estimated space")
        estimated_caption.setObjectName("metricCaption")
        estimated_group.addWidget(estimated_caption)
        estimated_group.addWidget(self.estimated_label)
        selected_group = QVBoxLayout()
        selected_group.setSpacing(2)
        selected_caption = QLabel("Selection")
        selected_caption.setObjectName("metricCaption")
        selected_group.addWidget(selected_caption)
        selected_group.addWidget(self.state_label)
        metrics.addLayout(estimated_group)
        metrics.addLayout(selected_group)
        top.addStretch(1)

        layout.addLayout(top)
        layout.addLayout(metrics)
        layout.addWidget(self.details_label)
        self.update_target(target)

    def update_target(self, target: CleanupTarget) -> None:
        self.title_label.setText(target.title)
        self.description_label.setText(target.description)
        self.checkbox.setEnabled(target.available and target.cleanup_supported)
        if not self.checkbox.isEnabled():
            self.checkbox.setChecked(False)
        self.status_label.setText(self._status_text(target))
        self.status_label.setProperty("statusKind", target.status.value)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.estimated_label.setText(format_bytes(target.estimated_bytes))
        self.details_label.setText(target.details)
        self._refresh_selection_state()

    def _refresh_selection_state(self) -> None:
        if not self.checkbox.isEnabled():
            text = "Not available on this system"
        elif self.checkbox.isChecked():
            text = "Included in the next cleanup"
        else:
            text = "Skipped for now"
        self.state_label.setText(text)

    def _status_text(self, target: CleanupTarget) -> str:
        mapping = {
            "available": "Ready to review",
            "clean": "Already tidy",
            "warning": "Needs extra care",
            "unavailable": "Not available",
        }
        return mapping.get(target.status.value, target.status.value.title())


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_TITLE}")
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        logo = QLabel()
        logo.setPixmap(load_logo_pixmap(88))
        logo.setAlignment(Qt.AlignCenter)

        title = QLabel(APP_TITLE)
        title.setObjectName("aboutTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("aboutSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        summary = QLabel(APP_SUMMARY)
        summary.setWordWrap(True)
        summary.setAlignment(Qt.AlignCenter)
        summary.setObjectName("aboutSummary")
        meta = QLabel(f"Version {__version__}\nMade by {AUTHOR_NAME}\n{AUTHOR_WEBSITE}")
        meta.setAlignment(Qt.AlignCenter)
        meta.setObjectName("aboutMeta")

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(summary)
        layout.addWidget(meta)
        layout.addWidget(close_button, alignment=Qt.AlignCenter)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(load_app_icon())
        self.resize(1024, 720)
        self.setMinimumSize(900, 650)
        self.cards: dict[str, TargetCard] = {}
        self.latest_targets: dict[str, CleanupTarget] = {}
        self.log_path = configure_logging()
        self._thread: QThread | None = None
        self._worker: Worker | None = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(18)

        header = self._build_header()
        layout.addWidget(header)

        section_header = QHBoxLayout()
        cards_title = QLabel("Cleanup Categories")
        cards_title.setObjectName("sectionTitle")
        cards_subtitle = QLabel("Choose what you want to review or clean. Nothing is removed until you confirm.")
        cards_subtitle.setObjectName("sectionSubtitle")
        cards_text = QVBoxLayout()
        cards_text.setSpacing(2)
        cards_text.addWidget(cards_title)
        cards_text.addWidget(cards_subtitle)
        section_header.addLayout(cards_text)
        section_header.addStretch(1)
        layout.addLayout(section_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_host = QWidget()
        self.grid = QGridLayout(scroll_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        scroll.setWidget(scroll_host)
        layout.addWidget(scroll, stretch=1)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.scan_button = QPushButton("Scan Again")
        self.preview_button = QPushButton("Preview Selected")
        self.clean_button = QPushButton("Clean Selected")
        self.logs_button = QPushButton("Open Log File")
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
        self._apply_button_icons()

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready to scan your system")
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        status_row.addWidget(self.progress, stretch=1)
        status_row.addWidget(self.status_label)
        layout.addLayout(status_row)

        log_group = QGroupBox("Activity")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(16, 18, 16, 16)
        log_layout.setSpacing(10)
        log_hint = QLabel("Klene records what it scanned, previewed, and cleaned here.")
        log_hint.setObjectName("sectionSubtitle")
        log_layout.addWidget(log_hint)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Monospace"))
        self.log_output.setMinimumHeight(180)
        self.log_output.setPlaceholderText("Activity details will appear here.")
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

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("hero")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(18)

        logo = QLabel()
        logo.setPixmap(load_logo_pixmap(84))
        logo.setFixedSize(QSize(92, 92))
        logo.setAlignment(Qt.AlignCenter)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        title = QLabel(APP_TITLE)
        title.setObjectName("title")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("subtitle")
        summary = QLabel(APP_HERO_SUMMARY)
        summary.setObjectName("heroSummary")
        summary.setWordWrap(True)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addWidget(self._chip("Preview first"))
        chips.addWidget(self._chip("No auto-delete"))
        chips.addWidget(self._chip("Arch-aware"))
        chips.addStretch(1)

        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        text_layout.addWidget(summary)
        text_layout.addLayout(chips)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)
        self.header_status = QLabel("Ready")
        self.header_status.setObjectName("heroStatus")
        self.last_scan_label = QLabel("No scan yet")
        self.last_scan_label.setObjectName("heroMeta")
        right_layout.addStretch(1)
        right_layout.addWidget(self.header_status, alignment=Qt.AlignRight)
        right_layout.addWidget(self.last_scan_label, alignment=Qt.AlignRight)
        right_layout.addStretch(1)

        layout.addWidget(logo)
        layout.addLayout(text_layout, stretch=1)
        layout.addLayout(right_layout)
        return frame

    def _chip(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("chip")
        return label

    def _apply_button_icons(self) -> None:
        style = self.style()
        self.scan_button.setIcon(style.standardIcon(QStyle.SP_BrowserReload))
        self.preview_button.setIcon(style.standardIcon(QStyle.SP_FileDialogContentsView))
        self.clean_button.setIcon(style.standardIcon(QStyle.SP_DialogApplyButton))
        self.logs_button.setIcon(style.standardIcon(QStyle.SP_FileDialogDetailedView))
        self.about_button.setIcon(style.standardIcon(QStyle.SP_MessageBoxInformation))

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
                background-color: #10161d;
                color: #e7ecf2;
            }
            QMenuBar {
                background-color: #10161d;
                color: #d8e1eb;
            }
            QMenuBar::item:selected, QMenu {
                background-color: #17202a;
            }
            QFrame#hero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #171f29, stop:1 #111820);
                border: 1px solid #293444;
                border-radius: 18px;
            }
            QLabel#title {
                font-size: 32px;
                font-weight: 700;
            }
            QLabel#subtitle {
                color: #9fb3c9;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#heroSummary, QLabel#sectionSubtitle, QLabel#aboutSummary {
                color: #9aabbe;
                font-size: 13px;
            }
            QLabel#heroStatus {
                color: #d6eaff;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#heroMeta, QLabel#aboutMeta {
                color: #8ea2b8;
                font-size: 12px;
            }
            QLabel#sectionTitle {
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#chip {
                background: #233246;
                border: 1px solid #314760;
                border-radius: 11px;
                color: #cfe3ff;
                padding: 5px 10px;
            }
            QFrame#card {
                background: #151c25;
                border: 1px solid #283141;
                border-radius: 16px;
            }
            QLabel#cardTitle {
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#cardDescription {
                color: #9db0c3;
                font-size: 13px;
            }
            QLabel#badge {
                background: #263444;
                border-radius: 11px;
                padding: 5px 11px;
                color: #cce0ff;
                font-weight: 600;
            }
            QLabel#badge[statusKind="clean"] {
                background: #1f3a2a;
                color: #b9f1c7;
            }
            QLabel#badge[statusKind="warning"] {
                background: #47361e;
                color: #ffd88f;
            }
            QLabel#badge[statusKind="unavailable"] {
                background: #2d333b;
                color: #b3beca;
            }
            QLabel#metricCaption {
                color: #8799ab;
                font-size: 11px;
                text-transform: uppercase;
            }
            QLabel#metricValue {
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#selectionState {
                color: #d4e3f3;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#cardNote {
                color: #8ea0b5;
                font-size: 12px;
            }
            QPushButton {
                background: #243245;
                border: 1px solid #32465e;
                border-radius: 11px;
                padding: 10px 15px;
                min-height: 18px;
            }
            QPushButton:hover {
                background: #2d405a;
            }
            QPushButton:pressed {
                background: #213044;
            }
            QPlainTextEdit, QGroupBox {
                background: #0c1117;
                border: 1px solid #283141;
                border-radius: 12px;
            }
            QGroupBox {
                font-weight: 700;
                margin-top: 8px;
                padding-top: 10px;
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
            QCheckBox {
                spacing: 0px;
            }
            QDialog {
                background-color: #10161d;
                color: #e7ecf2;
            }
            QLabel#aboutTitle {
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#aboutSubtitle {
                color: #9fb3c9;
                font-size: 14px;
                font-weight: 600;
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
        self.header_status.setText(message)
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
        self.set_busy(False, "Something went wrong")
        self.append_log(f"ERROR: {message}")
        build_message_box(
            self,
            title=APP_TITLE,
            icon=QMessageBox.Critical,
            text="Klene ran into a problem while working.",
            informative=message,
        ).exec()

    def _handle_worker_result(self, action: str, payload: object) -> None:
        status_messages = {
            "Scan": "Scan finished",
            "Preview": "Preview ready",
            "Clean": "Cleanup finished",
        }
        self.set_busy(False, status_messages.get(action, f"{action} finished"))
        if action == "Scan":
            self.populate_cards(payload)
            self.append_log("Scan finished. Review the categories below before cleaning anything.")
        elif action == "Preview":
            self._show_preview(payload)
        elif action == "Clean":
            self._show_cleanup_results(payload)

    def populate_cards(self, report: object) -> None:
        targets = getattr(report, "targets", [])
        generated_at = getattr(report, "generated_at", "")
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
        active_count = sum(1 for target in targets if target.status.value in {"available", "warning"})
        self.last_scan_label.setText(f"Last scan: {generated_at.replace('T', ' ').split('+')[0]} UTC")
        self.header_status.setText(f"{active_count} categories worth reviewing")

    def selected_keys(self) -> list[str]:
        return [key for key, card in self.cards.items() if card.checkbox.isChecked()]

    def start_scan(self) -> None:
        self.append_log("Scanning your system. Nothing will be deleted.")
        self._run_worker("Scan", scan_system)

    def preview_cleanup(self) -> None:
        keys = self.selected_keys()
        preview_lines = [
            "Preview only. Nothing will be deleted in this step.",
            "",
        ]
        for key in keys:
            target = self.latest_targets.get(key)
            if not target:
                continue
            preview_lines.append(f"{target.title} • {format_bytes(target.estimated_bytes)}")
            preview_lines.append(f"  {target.description}")
            if target.preview:
                preview_lines.extend(f"  - {line}" for line in target.preview[:10])
            else:
                preview_lines.append("  - No extra preview details were returned.")
            preview_lines.append("")
        self._run_worker("Preview", lambda: preview_lines)

    def _show_preview(self, lines: object) -> None:
        preview = "\n".join(lines if isinstance(lines, list) else [])
        if not preview:
            preview = "Nothing is selected yet.\n\nChoose one or more categories, then preview again."
        self.append_log(preview)
        build_message_box(
            self,
            title="Preview Cleanup",
            icon=QMessageBox.Information,
            text="Review the cleanup preview below.",
            informative="This step is always safe. No files or packages are removed here.",
            detailed=preview,
        ).exec()

    def clean_selected(self) -> None:
        keys = self.selected_keys()
        if not keys:
            QMessageBox.information(
                self,
                APP_TITLE,
                "Nothing is selected yet.\n\nPick one or more cleanup categories before running cleanup.",
            )
            return
        if "orphans" in keys:
            warning = build_message_box(
                self,
                title="Review Orphan Package Removal",
                icon=QMessageBox.Warning,
                text="Orphan package cleanup can remove installed packages.",
                informative="Only continue if you have reviewed the orphan list and are comfortable removing those packages.",
                buttons=QMessageBox.Yes | QMessageBox.No,
                default_button=QMessageBox.No,
            )
            if warning.exec() != QMessageBox.Yes:
                return
            warning = build_message_box(
                self,
                title="Final Orphan Package Check",
                icon=QMessageBox.Warning,
                text="Run orphan package cleanup?",
                informative="This is the last confirmation before Klene calls pacman to remove orphan packages.",
                buttons=QMessageBox.Yes | QMessageBox.No,
                default_button=QMessageBox.No,
            )
            if warning.exec() != QMessageBox.Yes:
                return
        confirm = build_message_box(
            self,
            title="Confirm Cleanup",
            icon=QMessageBox.Question,
            text="Clean the selected categories now?",
            informative="Klene will only clean the items you selected. Some tasks may ask for system authentication.",
            detailed="\n".join(
                f"- {self.latest_targets[key].title}" for key in keys if key in self.latest_targets
            ),
            buttons=QMessageBox.Yes | QMessageBox.No,
            default_button=QMessageBox.No,
        )
        if confirm.exec() != QMessageBox.Yes:
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
        results_list = results if isinstance(results, list) else []
        lines = []
        failures = []
        total_reclaimed = 0
        for result in results_list:
            label = self.latest_targets.get(result.key).title if result.key in self.latest_targets else result.key
            lines.append(f"{label}: {result.message}")
            if result.reclaimed_bytes:
                total_reclaimed += result.reclaimed_bytes
            if not result.success:
                failures.append(label)
        summary = (
            f"Cleanup finished. Estimated reclaimed space: {format_bytes(total_reclaimed)}."
            if total_reclaimed
            else "Cleanup finished."
        )
        if failures:
            summary = f"Cleanup finished with a few issues. Check the details below."
        self.append_log(summary)
        self.append_log("\n".join(lines))
        build_message_box(
            self,
            title="Cleanup Results",
            icon=QMessageBox.Information if not failures else QMessageBox.Warning,
            text=summary,
            informative="Klene has refreshed the scan so you can review the current state next.",
            detailed="\n".join(lines) or "No cleanup actions were run.",
        ).exec()
        self.start_scan()

    def open_logs(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path)))

    def show_about(self) -> None:
        AboutDialog(self).exec()


def create_splash() -> QSplashScreen:
    pixmap = QPixmap(560, 320)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    rounded = QPainterPath()
    rounded.addRoundedRect(0, 0, 560, 320, 24, 24)
    painter.setClipPath(rounded)
    painter.fillRect(0, 0, 560, 320, QColor("#111820"))
    painter.fillRect(0, 0, 560, 112, QColor(23, 31, 41, 180))
    painter.setPen(QColor("#2b3646"))
    painter.drawPath(rounded)
    logo = load_logo_pixmap(104)
    if not logo.isNull():
        painter.drawPixmap((560 - logo.width()) // 2, 42, logo)
    painter.setPen(QColor("#f4f8fc"))
    title_font = QFont()
    title_font.setPointSize(20)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(0, 182, 560, 34, Qt.AlignHCenter, APP_TITLE)
    subtitle_font = QFont()
    subtitle_font.setPointSize(11)
    subtitle_font.setWeight(QFont.DemiBold)
    painter.setFont(subtitle_font)
    painter.setPen(QColor("#9eb4c8"))
    painter.drawText(0, 216, 560, 24, Qt.AlignHCenter, APP_SUBTITLE)
    credit_font = QFont()
    credit_font.setPointSize(9)
    painter.setFont(credit_font)
    painter.setPen(QColor("#7f95aa"))
    painter.drawText(0, 268, 560, 22, Qt.AlignHCenter, AUTHOR_CREDIT)
    painter.end()

    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.FramelessWindowHint, True)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    splash.setEnabled(False)
    return splash


def launch_gui() -> None:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setWindowIcon(load_app_icon())
    splash = create_splash()
    splash.show()
    app.processEvents()
    window = MainWindow()

    def finish_startup() -> None:
        window.show()
        splash.finish(window)

    QTimer.singleShot(SPLASH_MIN_MS, finish_startup)
    app.exec()
