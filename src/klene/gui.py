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
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplashScreen,
    QStyle,
    QToolButton,
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
from klene.models import CleanupResult, CleanupStatus, CleanupTarget
from klene.scanner import scan_system
from klene.utils import format_bytes

APP_TITLE = APP_NAME
APP_SUBTITLE = APP_TAGLINE
APP_HERO_SUMMARY = APP_DESCRIPTION
SPLASH_MIN_MS = 900

SECTION_ORDER = ["recommended", "review", "advanced"]
SECTION_META = {
    "recommended": (
        "Recommended Cleanup",
        "These are the easiest cleanup areas for most Arch Linux users.",
    ),
    "review": (
        "Review First",
        "These can be useful, but it is worth taking a quick look before cleaning.",
    ),
    "advanced": (
        "Advanced / Package Changes",
        "These can affect installed packages and always deserve extra care.",
    ),
}


@dataclass(frozen=True, slots=True)
class CategoryUiSpec:
    section: str
    title: str
    description: str
    safety_label: str
    what_happens: str
    default_checked: bool


CATEGORY_UI: dict[str, CategoryUiSpec] = {
    "trash": CategoryUiSpec(
        "recommended",
        "Trash",
        "Empty files already moved to your trash.",
        "Recommended",
        "Klene removes files from ~/.local/share/Trash after you confirm.",
        True,
    ),
    "thumbnails": CategoryUiSpec(
        "recommended",
        "Thumbnails",
        "Clear image preview thumbnails that can be rebuilt automatically.",
        "Recommended",
        "Klene removes thumbnail cache files only. Apps can rebuild them later.",
        True,
    ),
    "user-cache": CategoryUiSpec(
        "recommended",
        "Low-risk cache",
        "Clean selected app cache folders that are usually safe to rebuild.",
        "Recommended",
        "Klene does not delete your whole ~/.cache folder.",
        True,
    ),
    "pacman-cache": CategoryUiSpec(
        "recommended",
        "Pacman cache",
        "Remove older cached package files while keeping recent versions.",
        "Recommended",
        "Klene uses paccache and keeps recent package versions.",
        True,
    ),
    "journal": CategoryUiSpec(
        "review",
        "System journal",
        "Trim older system logs to save space.",
        "Review first",
        "Klene asks journalctl to vacuum older logs when you confirm.",
        False,
    ),
    "aur-cache": CategoryUiSpec(
        "review",
        "AUR cache",
        "Clean build or package cache folders from yay or paru.",
        "Review first",
        "Klene only touches known yay and paru cache paths.",
        False,
    ),
    "flatpak-cache": CategoryUiSpec(
        "review",
        "Flatpak unused data",
        "Review unused Flatpak data when Flatpak is installed.",
        "Review first",
        "Klene asks Flatpak to remove unused data only after confirmation.",
        False,
    ),
    "orphans": CategoryUiSpec(
        "advanced",
        "Orphan packages",
        "Packages no longer required by other installed packages.",
        "Advanced",
        "This can remove installed packages and always needs extra confirmation.",
        False,
    ),
}


def app_logo_path() -> Path:
    return packaged_logo_path()


def load_logo_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(str(app_logo_path()))
    if pixmap.isNull():
        return QPixmap()
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def load_app_icon() -> QIcon:
    return QIcon(str(app_logo_path()))


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


class PreviewDialog(QDialog):
    def __init__(self, title: str, intro: str, details: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        intro_label = QLabel(intro)
        intro_label.setObjectName("dialogIntro")
        intro_label.setWordWrap(True)

        details_view = QPlainTextEdit()
        details_view.setReadOnly(True)
        details_view.setPlainText(details)
        details_view.setObjectName("dialogDetails")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout.addWidget(intro_label)
        layout.addWidget(details_view, stretch=1)
        layout.addWidget(buttons)


class TargetCard(QFrame):
    selection_changed = Signal()

    def __init__(self, key: str, spec: CategoryUiSpec) -> None:
        super().__init__()
        self.target_key = key
        self.spec = spec
        self.target: CleanupTarget | None = None
        self.setObjectName("card")
        self.setProperty("safetyLevel", spec.section)
        self.setProperty("selectedCard", False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.checkbox = QCheckBox()
        self.checkbox.toggled.connect(self._on_toggled)
        top.addWidget(self.checkbox, alignment=Qt.AlignTop)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        self.title_label = QLabel(spec.title)
        self.title_label.setObjectName("cardTitle")
        self.description_label = QLabel(spec.description)
        self.description_label.setObjectName("cardDescription")
        self.description_label.setWordWrap(True)
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.description_label)
        top.addLayout(title_layout, stretch=1)

        badge_layout = QVBoxLayout()
        badge_layout.setSpacing(6)
        self.safety_badge = QLabel(spec.safety_label)
        self.safety_badge.setObjectName("safetyBadge")
        self.safety_badge.setProperty("safetyLevel", spec.section)
        self.status_badge = QLabel("Ready")
        self.status_badge.setObjectName("statusBadge")
        badge_layout.addWidget(self.safety_badge, alignment=Qt.AlignRight)
        badge_layout.addWidget(self.status_badge, alignment=Qt.AlignRight)
        top.addLayout(badge_layout)

        metric_layout = QHBoxLayout()
        metric_layout.setSpacing(18)
        size_group = QVBoxLayout()
        size_group.setSpacing(2)
        size_caption = QLabel("Estimated cleanup")
        size_caption.setObjectName("metricCaption")
        self.size_value = QLabel("Unknown")
        self.size_value.setObjectName("metricValue")
        size_group.addWidget(size_caption)
        size_group.addWidget(self.size_value)

        selection_group = QVBoxLayout()
        selection_group.setSpacing(2)
        selection_caption = QLabel("Selection")
        selection_caption.setObjectName("metricCaption")
        self.selection_value = QLabel("Not selected")
        self.selection_value.setObjectName("selectionValue")
        selection_group.addWidget(selection_caption)
        selection_group.addWidget(self.selection_value)

        metric_layout.addLayout(size_group)
        metric_layout.addLayout(selection_group)
        metric_layout.addStretch(1)

        self.info_line = QLabel()
        self.info_line.setObjectName("cardInfo")
        self.info_line.setWordWrap(True)

        self.what_happens = QLabel(f"What happens: {spec.what_happens}")
        self.what_happens.setObjectName("whatHappens")
        self.what_happens.setWordWrap(True)

        layout.addLayout(top)
        layout.addLayout(metric_layout)
        layout.addWidget(self.info_line)
        layout.addWidget(self.what_happens)

    def update_target(self, target: CleanupTarget) -> None:
        previous_target = self.target
        self.target = target
        can_select = target.available and target.cleanup_supported and target.status != CleanupStatus.CLEAN
        default_checked = self.spec.default_checked and can_select
        previous = self.checkbox.isChecked()
        self.checkbox.blockSignals(True)
        if not can_select:
            self.checkbox.setChecked(False)
        elif previous_target is None:
            self.checkbox.setChecked(default_checked)
        self.checkbox.setEnabled(can_select)
        self.checkbox.blockSignals(False)

        self.size_value.setText(format_bytes(target.estimated_bytes))
        self.status_badge.setText(self._status_text(target))
        self.status_badge.setProperty("statusKind", self._status_kind(target))
        self._style_widget(self.status_badge)
        self.info_line.setText(self._info_text(target))
        self._refresh_selection_state()

    def set_checked(self, checked: bool) -> None:
        if self.checkbox.isEnabled():
            self.checkbox.setChecked(checked)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked() and self.checkbox.isEnabled()

    def has_unknown_size(self) -> bool:
        return self.target is not None and self.target.estimated_bytes is None and self.is_checked()

    def _status_text(self, target: CleanupTarget) -> str:
        if target.status == CleanupStatus.CLEAN:
            return "Not needed"
        if target.status == CleanupStatus.UNAVAILABLE:
            if "not installed" in target.details.lower():
                return "Needs setup"
            return "Not found"
        if target.status == CleanupStatus.WARNING:
            return "Needs review"
        return "Ready"

    def _status_kind(self, target: CleanupTarget) -> str:
        if target.status == CleanupStatus.CLEAN:
            return "clean"
        if target.status == CleanupStatus.UNAVAILABLE:
            return "unavailable"
        if target.status == CleanupStatus.WARNING:
            return "warning"
        return "ready"

    def _info_text(self, target: CleanupTarget) -> str:
        if target.status == CleanupStatus.CLEAN:
            return target.details or "Nothing to clean here right now."
        return target.details

    def _on_toggled(self) -> None:
        self._refresh_selection_state()
        self.selection_changed.emit()

    def _refresh_selection_state(self) -> None:
        if not self.checkbox.isEnabled():
            text = "Not selected"
        elif self.checkbox.isChecked():
            text = "Selected"
        else:
            text = "Not selected"
        self.selection_value.setText(text)
        self.setProperty("selectedCard", self.checkbox.isChecked())
        self._style_widget(self)

    def _style_widget(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


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
        self.resize(1000, 720)
        self.setMinimumSize(900, 650)

        self.log_path = configure_logging()
        self.latest_targets: dict[str, CleanupTarget] = {}
        self.cards: dict[str, TargetCard] = {}
        self.scan_completed = False
        self.preview_ready = False
        self._thread: QThread | None = None
        self._worker: Worker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_summary_panel())
        layout.addWidget(self._build_categories_panel(), stretch=1)
        layout.addWidget(self._build_action_panel())
        layout.addWidget(self._build_log_panel())

        self._apply_styles()
        self._wire_actions()
        self._build_menu()
        self._refresh_summary()
        self._update_action_state()

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
        logo.setPixmap(load_logo_pixmap(82))
        logo.setFixedSize(QSize(90, 90))
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
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        text_layout.addWidget(summary)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)
        self.header_status = QLabel("Ready to scan your system")
        self.header_status.setObjectName("heroStatus")
        self.last_scan_label = QLabel("Last scan: not run yet")
        self.last_scan_label.setObjectName("heroMeta")
        self.scan_button = QPushButton("Scan My System")
        self.scan_button.setObjectName("primaryButton")
        self.scan_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        right_layout.addWidget(self.header_status, alignment=Qt.AlignRight)
        right_layout.addWidget(self.last_scan_label, alignment=Qt.AlignRight)
        right_layout.addWidget(self.scan_button, alignment=Qt.AlignRight)
        right_layout.addStretch(1)

        layout.addWidget(logo)
        layout.addLayout(text_layout, stretch=1)
        layout.addLayout(right_layout)
        return frame

    def _build_summary_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("summaryPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self.summary_headline = QLabel()
        self.summary_headline.setObjectName("summaryHeadline")
        self.summary_detail = QLabel()
        self.summary_detail.setObjectName("summaryDetail")
        self.summary_detail.setWordWrap(True)

        metrics = QHBoxLayout()
        metrics.setSpacing(20)
        self.total_found_label = QLabel()
        self.total_found_label.setObjectName("summaryMetric")
        self.total_selected_label = QLabel()
        self.total_selected_label.setObjectName("summaryMetric")
        self.advanced_selected_label = QLabel()
        self.advanced_selected_label.setObjectName("summaryMetric")
        metrics.addWidget(self.total_found_label)
        metrics.addWidget(self.total_selected_label)
        metrics.addWidget(self.advanced_selected_label)
        metrics.addStretch(1)

        layout.addWidget(self.summary_headline)
        layout.addWidget(self.summary_detail)
        layout.addLayout(metrics)
        return frame

    def _build_categories_panel(self) -> QWidget:
        container = QFrame()
        container.setObjectName("categoriesPanel")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        panel_header = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        title = QLabel("Cleanup Categories")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Klene groups cleanup areas by how safe they usually are. Preview always comes first."
        )
        subtitle.setObjectName("sectionSubtitle")
        subtitle.setWordWrap(True)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        panel_header.addLayout(header_text)
        panel_header.addStretch(1)
        outer.addLayout(panel_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("categoryScroll")
        host = QWidget()
        self.sections_layout = QVBoxLayout(host)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(16)
        self.section_frames: dict[str, QWidget] = {}
        self.section_grids: dict[str, QGridLayout] = {}
        self.section_empty_labels: dict[str, QLabel] = {}

        for section in SECTION_ORDER:
            title_text, subtitle_text = SECTION_META[section]
            frame = QFrame()
            frame.setObjectName("sectionFrame")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(10)
            title = QLabel(title_text)
            title.setObjectName("sectionTitle")
            subtitle = QLabel(subtitle_text)
            subtitle.setObjectName("sectionSubtitle")
            subtitle.setWordWrap(True)
            empty = QLabel("Run a scan to load cleanup categories.")
            empty.setObjectName("emptyState")
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(14)
            layout.addWidget(title)
            layout.addWidget(subtitle)
            layout.addWidget(empty)
            layout.addLayout(grid)
            self.sections_layout.addWidget(frame)
            self.section_frames[section] = frame
            self.section_grids[section] = grid
            self.section_empty_labels[section] = empty

        scroll.setWidget(host)
        outer.addWidget(scroll, stretch=1)
        return container

    def _build_action_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("actionPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        steps = QLabel("Step 1: Scan   •   Step 2: Preview selected cleanup   •   Step 3: Clean selected")
        steps.setObjectName("stepsLabel")

        summary_row = QHBoxLayout()
        summary_row.setSpacing(14)
        self.selected_areas_label = QLabel("Selected: 0 areas")
        self.selected_areas_label.setObjectName("summaryMetric")
        self.estimated_cleanup_label = QLabel("Estimated cleanup: 0 B")
        self.estimated_cleanup_label.setObjectName("summaryMetric")
        self.unknown_size_label = QLabel("")
        self.unknown_size_label.setObjectName("summaryMetric")
        summary_row.addWidget(self.selected_areas_label)
        summary_row.addWidget(self.estimated_cleanup_label)
        summary_row.addWidget(self.unknown_size_label)
        summary_row.addStretch(1)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.preview_button = QPushButton("Preview Selected")
        self.preview_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.clean_button = QPushButton("Clean Selected")
        self.clean_button.setObjectName("accentButton")
        self.clean_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.about_button = QPushButton("About")
        self.about_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.logs_button = QPushButton("Open Log File")
        self.logs_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.clean_button)
        button_row.addWidget(self.about_button)
        button_row.addWidget(self.logs_button)
        button_row.addStretch(1)

        layout.addWidget(steps)
        layout.addLayout(summary_row)
        layout.addLayout(button_row)
        return frame

    def _build_log_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("logPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.log_toggle = QToolButton()
        self.log_toggle.setText("Show Activity Log")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(False)
        self.log_toggle.setArrowType(Qt.RightArrow)
        self.log_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.addWidget(self.log_toggle)
        header.addStretch(1)

        self.log_hint = QLabel("Most people can ignore this unless they want more detail.")
        self.log_hint.setObjectName("sectionSubtitle")
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Monospace"))
        self.log_output.setFixedHeight(150)
        self.log_output.setPlaceholderText("Activity details will appear here after a scan or preview.")
        self.log_output.hide()
        self.log_hint.hide()

        layout.addLayout(header)
        layout.addWidget(self.log_hint)
        layout.addWidget(self.log_output)
        return frame

    def _wire_actions(self) -> None:
        self.scan_button.clicked.connect(self.start_scan)
        self.preview_button.clicked.connect(self.preview_cleanup)
        self.clean_button.clicked.connect(self.clean_selected)
        self.about_button.clicked.connect(self.show_about)
        self.logs_button.clicked.connect(self.open_logs)
        self.log_toggle.toggled.connect(self._toggle_log_panel)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #14191f;
                color: #edf2f7;
            }
            QMenuBar {
                background-color: #14191f;
                color: #dbe4ec;
            }
            QMenuBar::item:selected, QMenu {
                background-color: #1b232c;
            }
            QFrame#hero, QFrame#summaryPanel, QFrame#sectionFrame, QFrame#actionPanel, QFrame#logPanel {
                background: #1a2129;
                border: 1px solid #2a3440;
                border-radius: 18px;
            }
            QLabel#title {
                font-size: 31px;
                font-weight: 700;
            }
            QLabel#subtitle {
                color: #a9b8c8;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#heroSummary, QLabel#sectionSubtitle, QLabel#aboutSummary, QLabel#dialogIntro, QLabel#emptyState {
                color: #a1afbf;
                font-size: 13px;
            }
            QLabel#heroStatus {
                color: #dbe8f8;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#heroMeta, QLabel#aboutMeta {
                color: #91a2b3;
                font-size: 12px;
            }
            QLabel#summaryHeadline {
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#summaryDetail, QLabel#cardInfo {
                color: #b6c3d2;
                font-size: 13px;
            }
            QLabel#summaryMetric, QLabel#stepsLabel {
                color: #d9e5f2;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#sectionTitle {
                font-size: 18px;
                font-weight: 700;
            }
            QFrame#card {
                background: #202832;
                border: 1px solid #313c49;
                border-radius: 16px;
            }
            QFrame#card[selectedCard="true"] {
                border: 1px solid #69b1ff;
                background: #223141;
            }
            QFrame#card[safetyLevel="advanced"] {
                background: #282128;
                border: 1px solid #5f4a55;
            }
            QFrame#card[safetyLevel="advanced"][selectedCard="true"] {
                background: #342a33;
                border: 1px solid #f0b4c0;
            }
            QLabel#cardTitle {
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#cardDescription {
                color: #acbac9;
                font-size: 13px;
            }
            QLabel#metricCaption {
                color: #8496a8;
                font-size: 11px;
            }
            QLabel#metricValue {
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#selectionValue {
                color: #d9e6f3;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#whatHappens {
                color: #94a4b5;
                font-size: 12px;
            }
            QLabel#safetyBadge, QLabel#statusBadge {
                border-radius: 11px;
                padding: 5px 10px;
                font-weight: 600;
                font-size: 12px;
            }
            QLabel#safetyBadge[safetyLevel="recommended"] {
                background: #21372a;
                color: #c2f2cf;
            }
            QLabel#safetyBadge[safetyLevel="review"] {
                background: #3a3220;
                color: #ffe3a8;
            }
            QLabel#safetyBadge[safetyLevel="advanced"] {
                background: #472f39;
                color: #ffd3dc;
            }
            QLabel#statusBadge[statusKind="ready"] {
                background: #243849;
                color: #cfe4ff;
            }
            QLabel#statusBadge[statusKind="warning"] {
                background: #49391d;
                color: #ffd88f;
            }
            QLabel#statusBadge[statusKind="clean"] {
                background: #233328;
                color: #c4efcc;
            }
            QLabel#statusBadge[statusKind="unavailable"] {
                background: #2f353d;
                color: #c3ccd6;
            }
            QPushButton, QToolButton {
                background: #283444;
                border: 1px solid #39506a;
                border-radius: 12px;
                padding: 10px 15px;
                min-height: 18px;
                color: #ecf2f8;
            }
            QPushButton:hover, QToolButton:hover {
                background: #314256;
            }
            QPushButton:disabled {
                background: #1f2730;
                border-color: #2a3440;
                color: #718194;
            }
            QPushButton#primaryButton {
                background: #74b7ff;
                border-color: #74b7ff;
                color: #102030;
                font-weight: 700;
            }
            QPushButton#accentButton {
                background: #5ea7ff;
                border-color: #5ea7ff;
                color: #11202f;
                font-weight: 700;
            }
            QProgressBar {
                background: #151c23;
                border: 1px solid #2b3642;
                border-radius: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #6db3ff;
                border-radius: 8px;
            }
            QDialog {
                background-color: #14191f;
                color: #edf2f7;
            }
            QLabel#aboutTitle {
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#aboutSubtitle {
                color: #9fb2c6;
                font-size: 14px;
                font-weight: 600;
            }
            QPlainTextEdit#dialogDetails, QPlainTextEdit {
                background: #12171d;
                border: 1px solid #2b3642;
                border-radius: 12px;
            }
            """
        )

    def append_log(self, line: str) -> None:
        self.log_output.appendPlainText(line)

    def _toggle_log_panel(self, checked: bool) -> None:
        self.log_toggle.setText("Hide Activity Log" if checked else "Show Activity Log")
        self.log_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.log_hint.setVisible(checked)
        self.log_output.setVisible(checked)

    def set_busy(self, busy: bool, message: str) -> None:
        self.header_status.setText(message)
        self.scan_button.setEnabled(not busy)
        if busy:
            self.preview_button.setEnabled(False)
            self.clean_button.setEnabled(False)
        else:
            self._update_action_state()

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
        self.append_log(f"ERROR: {message}")
        self.set_busy(False, "Something went wrong")
        box = QMessageBox(self)
        box.setWindowTitle(APP_TITLE)
        box.setIcon(QMessageBox.Critical)
        box.setText("Klene ran into a problem while working.")
        box.setInformativeText(message)
        box.addButton("Close", QMessageBox.AcceptRole)
        box.exec()

    def _handle_worker_result(self, action: str, payload: object) -> None:
        if action == "Scan":
            self.scan_completed = True
            self.preview_ready = False
            self.populate_cards(payload)
            self.header_status.setText("Scan complete")
            self.last_scan_label.setText("Last scan: just now")
            self.append_log("Scan complete. Review the cleanup areas below before choosing anything.")
        elif action == "Preview":
            self.preview_ready = True
            self._show_preview(payload)
            self.append_log("Preview generated. Nothing has been removed.")
        elif action == "Clean":
            self.preview_ready = False
            self._show_cleanup_results(payload)
        self.set_busy(False, self.header_status.text())
        self._refresh_summary()
        self._update_action_state()

    def populate_cards(self, report: object) -> None:
        targets = getattr(report, "targets", [])
        self.latest_targets = {target.key: target for target in targets}
        grouped = {section: [] for section in SECTION_ORDER}
        for key, spec in CATEGORY_UI.items():
            target = self.latest_targets.get(key)
            if target is None:
                continue
            grouped[spec.section].append((key, target))

        for section in SECTION_ORDER:
            grid = self.section_grids[section]
            while grid.count():
                item = grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)

            items = grouped[section]
            self.section_empty_labels[section].setVisible(not items)
            if not items:
                self.section_empty_labels[section].setText("Nothing to show here until Klene finds matching cleanup areas.")
                continue

            for index, (key, target) in enumerate(items):
                row, col = divmod(index, 2)
                card = self.cards.get(key)
                if card is None:
                    card = TargetCard(key, CATEGORY_UI[key])
                    card.selection_changed.connect(self._on_selection_changed)
                    self.cards[key] = card
                card.update_target(target)
                grid.addWidget(card, row, col)

        self._refresh_summary()

    def selected_keys(self) -> list[str]:
        return [key for key, card in self.cards.items() if card.is_checked()]

    def _on_selection_changed(self) -> None:
        self.preview_ready = False
        self._refresh_summary()
        self._update_action_state()

    def _refresh_summary(self) -> None:
        selected_keys = self.selected_keys()
        selected_targets = [self.latest_targets[key] for key in selected_keys if key in self.latest_targets]
        selected_known = sum(target.estimated_bytes or 0 for target in selected_targets)
        unknown_selected = any(target.estimated_bytes is None for target in selected_targets)
        active_found = sum(
            1
            for target in self.latest_targets.values()
            if target.status in {CleanupStatus.AVAILABLE, CleanupStatus.WARNING}
        )
        advanced_selected = "orphans" in selected_keys

        if not self.scan_completed:
            self.summary_headline.setText("Start with a scan.")
            self.summary_detail.setText(
                "Klene will look for safe cleanup opportunities and explain everything before you clean."
            )
            self.total_found_label.setText("Cleanup areas found: 0")
            self.total_selected_label.setText("Selected: 0")
            self.advanced_selected_label.setText("Advanced items selected: No")
        else:
            if selected_keys:
                self.summary_headline.setText(
                    f"{format_bytes(selected_known)} selected from cleanup areas."
                )
            else:
                self.summary_headline.setText("Choose the cleanup areas you want to review.")
            safety_note = "Klene previews everything first. Nothing is removed until you confirm."
            if advanced_selected:
                safety_note = (
                    "Advanced items are selected. Klene will ask for extra confirmation before package changes."
                )
            self.summary_detail.setText(safety_note)
            self.total_found_label.setText(f"Cleanup areas found: {active_found}")
            self.total_selected_label.setText(f"Selected: {len(selected_keys)}")
            self.advanced_selected_label.setText(
                f"Advanced items selected: {'Yes' if advanced_selected else 'No'}"
            )

        self.selected_areas_label.setText(f"Selected: {len(selected_keys)} areas")
        self.estimated_cleanup_label.setText(f"Estimated cleanup: {format_bytes(selected_known)}")
        self.unknown_size_label.setText("Some selected items have unknown size." if unknown_selected else "")

    def _update_action_state(self) -> None:
        has_selection = bool(self.selected_keys())
        self.preview_button.setEnabled(self.scan_completed and has_selection)
        self.clean_button.setEnabled(self.scan_completed and has_selection and self.preview_ready)

    def start_scan(self) -> None:
        self.preview_ready = False
        self.append_log("Scanning your system. Nothing will be deleted.")
        self._run_worker("Scan", scan_system)

    def preview_cleanup(self) -> None:
        keys = self.selected_keys()
        grouped: dict[str, list[str]] = {}
        for key in keys:
            target = self.latest_targets.get(key)
            if target is None:
                continue
            section_name = SECTION_META[CATEGORY_UI[key].section][0]
            grouped.setdefault(section_name, [])
            grouped[section_name].append(f"{CATEGORY_UI[key].title} • {format_bytes(target.estimated_bytes)}")
            grouped[section_name].append(f"  {CATEGORY_UI[key].what_happens}")
            if target.preview:
                grouped[section_name].extend(f"  - {line}" for line in target.preview[:10])
            else:
                grouped[section_name].append("  - No extra preview details were returned.")
            grouped[section_name].append("")

        lines = ["This is only a preview. Nothing has been removed.", ""]
        for section in SECTION_ORDER:
            section_name = SECTION_META[section][0]
            if section_name not in grouped:
                continue
            lines.append(section_name)
            lines.append("-" * len(section_name))
            lines.extend(grouped[section_name])

        self._run_worker("Preview", lambda: lines)

    def _show_preview(self, lines: object) -> None:
        preview = "\n".join(lines if isinstance(lines, list) else [])
        if not preview:
            preview = "Nothing is selected yet.\n\nChoose one or more categories, then preview again."
        self.append_log(preview)
        PreviewDialog(
            "Preview Selected Cleanup",
            "This is only a preview. Nothing has been removed.",
            preview,
            self,
        ).exec()

    def clean_selected(self) -> None:
        keys = self.selected_keys()
        if not keys:
            box = QMessageBox(self)
            box.setWindowTitle(APP_TITLE)
            box.setIcon(QMessageBox.Information)
            box.setText("Nothing is selected yet.")
            box.setInformativeText("Pick one or more cleanup areas before running cleanup.")
            box.addButton("Close", QMessageBox.AcceptRole)
            box.exec()
            return

        details = "\n".join(
            f"- {CATEGORY_UI[key].title} ({format_bytes(self.latest_targets[key].estimated_bytes)})"
            for key in keys
            if key in self.latest_targets
        )

        if "orphans" in keys:
            if not self._confirm_orphan_cleanup():
                return

        box = QMessageBox(self)
        box.setWindowTitle("Confirm Cleanup")
        box.setIcon(QMessageBox.Warning)
        box.setText("Klene is ready to clean the selected areas.")
        box.setInformativeText(
            "This cannot always be undone. Review the list below before continuing."
        )
        box.setDetailedText(details)
        continue_button = box.addButton("I Understand, Continue", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() != continue_button:
            return

        self._run_worker("Clean", lambda: self._perform_selected_cleanup(keys))

    def _confirm_orphan_cleanup(self) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Orphan Package Cleanup")
        box.setIcon(QMessageBox.Warning)
        box.setText("Orphan package cleanup can remove installed packages.")
        box.setInformativeText(
            "Only continue if you reviewed the package list and understand what will be removed."
        )
        continue_button = box.addButton("I Understand, Continue", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() == continue_button

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
            label = CATEGORY_UI.get(result.key, CategoryUiSpec("", result.key, "", "", "", False)).title
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
            summary = "Cleanup finished with a few issues. Review the details below."
        self.append_log(summary)
        self.append_log("\n".join(lines))
        PreviewDialog(
            "Cleanup Results",
            summary,
            "\n".join(lines) or "No cleanup actions were run.",
            self,
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
