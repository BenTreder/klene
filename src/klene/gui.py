from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QSize, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
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
    QPushButton,
    QSizePolicy,
    QSplashScreen,
    QStackedWidget,
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
from klene.utils import format_bytes, format_display_path, shorten_home_paths

APP_TITLE = APP_NAME
APP_SUBTITLE = APP_TAGLINE
APP_HERO_SUMMARY = APP_DESCRIPTION
SPLASH_MIN_MS = 900

THEME = {
    "background": "#111827",
    "panel": "#1a2332",
    "panel_alt": "#202c3c",
    "panel_soft": "#243245",
    "text": "#f4f7fb",
    "muted_text": "#9fb0c4",
    "border": "#304154",
    "primary": "#69b2ff",
    "recommended": "#4ec7a0",
    "review": "#7bc4ff",
    "advanced": "#ffb264",
    "success": "#72d1ae",
    "warning": "#ffd27d",
    "danger": "#ffb0a4",
}

SECTION_ORDER = ["recommended", "review", "advanced"]
SECTION_META = {
    "recommended": (
        "Recommended",
        "Recommended Cleanup",
        "Good first cleanup choices for most Arch users.",
    ),
    "review": (
        "Review First",
        "Review First",
        "Useful cleanup areas worth checking before you clean.",
    ),
    "advanced": (
        "Advanced",
        "Advanced / Package Changes",
        "Package changes need extra care and extra confirmation.",
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
        "Klene only cleans known safer cache folders, not your whole ~/.cache directory.",
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


class DetailDialog(QDialog):
    def __init__(self, title: str, intro: str, details: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        intro_label = QLabel(intro)
        intro_label.setObjectName("dialogIntro")
        intro_label.setWordWrap(True)

        detail_view = QPlainTextEdit()
        detail_view.setReadOnly(True)
        detail_view.setPlainText(details)
        detail_view.setObjectName("dialogDetails")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout.addWidget(intro_label)
        layout.addWidget(detail_view, stretch=1)
        layout.addWidget(buttons)


class TargetCard(QFrame):
    selection_changed = Signal()

    def __init__(self, key: str, spec: CategoryUiSpec) -> None:
        super().__init__()
        self.target_key = key
        self.spec = spec
        self.target: CleanupTarget | None = None
        self.setObjectName("targetCard")
        self.setProperty("section", spec.section)
        self.setProperty("selected", False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.checkbox = QCheckBox()
        self.checkbox.toggled.connect(self._on_toggled)
        header.addWidget(self.checkbox, alignment=Qt.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        self.title_label = QLabel(spec.title)
        self.title_label.setObjectName("cardTitle")
        self.description_label = QLabel(spec.description)
        self.description_label.setObjectName("cardDescription")
        self.description_label.setWordWrap(True)
        title_col.addWidget(self.title_label)
        title_col.addWidget(self.description_label)
        header.addLayout(title_col, stretch=1)

        self.safety_badge = QLabel(spec.safety_label)
        self.safety_badge.setObjectName("safetyBadge")
        self.safety_badge.setProperty("section", spec.section)
        header.addWidget(self.safety_badge, alignment=Qt.AlignTop)

        metrics = QHBoxLayout()
        metrics.setSpacing(18)
        size_col = QVBoxLayout()
        size_col.setSpacing(2)
        size_caption = QLabel("Estimated cleanup")
        size_caption.setObjectName("metricCaption")
        self.size_value = QLabel("Unknown")
        self.size_value.setObjectName("metricValue")
        size_col.addWidget(size_caption)
        size_col.addWidget(self.size_value)

        status_col = QVBoxLayout()
        status_col.setSpacing(2)
        status_caption = QLabel("Status")
        status_caption.setObjectName("metricCaption")
        self.status_value = QLabel("Not selected")
        self.status_value.setObjectName("statusText")
        status_col.addWidget(status_caption)
        status_col.addWidget(self.status_value)
        metrics.addLayout(size_col)
        metrics.addLayout(status_col)
        metrics.addStretch(1)

        self.info_badge = QLabel("Ready")
        self.info_badge.setObjectName("statusBadge")
        metrics.addWidget(self.info_badge, alignment=Qt.AlignBottom)

        self.what_happens = QLabel(f"What happens: {spec.what_happens}")
        self.what_happens.setObjectName("whatHappens")
        self.what_happens.setWordWrap(True)

        layout.addLayout(header)
        layout.addLayout(metrics)
        layout.addWidget(self.what_happens)

    def update_target(self, target: CleanupTarget) -> None:
        previous_target = self.target
        self.target = target
        can_select = target.available and target.cleanup_supported and target.status != CleanupStatus.CLEAN
        default_checked = self.spec.default_checked and can_select

        self.checkbox.blockSignals(True)
        if not can_select:
            self.checkbox.setChecked(False)
        elif previous_target is None:
            self.checkbox.setChecked(default_checked)
        self.checkbox.setEnabled(can_select)
        self.checkbox.blockSignals(False)

        self.size_value.setText(format_bytes(target.estimated_bytes))
        self.info_badge.setText(self._status_badge_text(target))
        self.info_badge.setProperty("statusKind", self._status_kind(target))
        self.status_value.setText("Selected" if self.is_checked() else "Not selected")
        self.what_happens.setText(f"What happens: {self.spec.what_happens}")
        if target.status == CleanupStatus.UNAVAILABLE or target.status == CleanupStatus.CLEAN:
            self.what_happens.setText(shorten_home_paths(target.details))
        self._refresh_style()

    def is_checked(self) -> bool:
        return self.checkbox.isEnabled() and self.checkbox.isChecked()

    def set_checked(self, checked: bool) -> None:
        if self.checkbox.isEnabled():
            self.checkbox.setChecked(checked)

    def has_unknown_size(self) -> bool:
        return self.target is not None and self.target.estimated_bytes is None and self.is_checked()

    def _status_badge_text(self, target: CleanupTarget) -> str:
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

    def _on_toggled(self) -> None:
        self.status_value.setText("Selected" if self.is_checked() else "Not selected")
        self._refresh_style()
        self.selection_changed.emit()

    def _refresh_style(self) -> None:
        self.setProperty("selected", self.is_checked())
        self.style().unpolish(self)
        self.style().polish(self)
        self.info_badge.style().unpolish(self.info_badge)
        self.info_badge.style().polish(self.info_badge)


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
        self.page_layout = QVBoxLayout(central)
        self.page_layout.setContentsMargins(22, 18, 22, 18)
        self.page_layout.setSpacing(16)

        self.page_layout.addWidget(self._build_header())
        self.page_layout.addWidget(self._build_summary_panel())
        self.page_layout.addWidget(self._build_category_area(), stretch=1)
        self.page_layout.addWidget(self._build_action_bar())
        self.page_layout.addWidget(self._build_log_panel())

        self._apply_styles()
        self._wire_actions()
        self._build_menu()
        self.section_tabs.hide()
        self.section_stack.hide()
        self._refresh_summary()
        self._update_action_state()

    def _build_menu(self) -> None:
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(about_action)

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("heroPanel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(18)

        logo = QLabel()
        logo.setPixmap(load_logo_pixmap(82))
        logo.setFixedSize(QSize(92, 92))
        logo.setAlignment(Qt.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        title = QLabel(APP_TITLE)
        title.setObjectName("heroTitle")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("heroSubtitle")
        summary = QLabel(APP_HERO_SUMMARY)
        summary.setObjectName("heroSummary")
        summary.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        text_col.addWidget(summary)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        self.header_status = QLabel("Ready to scan your system")
        self.header_status.setObjectName("heroStatus")
        self.last_scan_label = QLabel("Last scan: not run yet")
        self.last_scan_label.setObjectName("heroMeta")
        self.scan_button = QPushButton("Scan My System")
        self.scan_button.setObjectName("primaryAction")
        self.scan_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        right_col.addWidget(self.header_status, alignment=Qt.AlignRight)
        right_col.addWidget(self.last_scan_label, alignment=Qt.AlignRight)
        right_col.addWidget(self.scan_button, alignment=Qt.AlignRight)
        right_col.addStretch(1)

        layout.addWidget(logo)
        layout.addLayout(text_col, stretch=1)
        layout.addLayout(right_col)
        return frame

    def _build_summary_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("summaryPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.summary_title = QLabel()
        self.summary_title.setObjectName("summaryTitle")
        self.summary_detail = QLabel()
        self.summary_detail.setObjectName("summaryDetail")
        self.summary_detail.setWordWrap(True)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(12)
        self.summary_size = self._metric_chip("Selected cleanup", "0 B")
        self.summary_count = self._metric_chip("Selected areas", "0")
        self.summary_review = self._metric_chip("Review-first selected", "No")
        self.summary_advanced = self._metric_chip("Advanced selected", "No")
        self.summary_safety = self._metric_chip("Safety", "Preview required")
        for widget in [
            self.summary_size,
            self.summary_count,
            self.summary_review,
            self.summary_advanced,
            self.summary_safety,
        ]:
            chip_row.addWidget(widget)
        chip_row.addStretch(1)

        layout.addWidget(self.summary_title)
        layout.addWidget(self.summary_detail)
        layout.addLayout(chip_row)
        return frame

    def _metric_chip(self, label: str, value: str) -> QWidget:
        frame = QFrame()
        frame.setObjectName("metricChip")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        label_widget = QLabel(label)
        label_widget.setObjectName("metricChipLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("metricChipValue")
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        frame.value_widget = value_widget  # type: ignore[attr-defined]
        return frame

    def _build_category_area(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("contentPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.empty_state = QFrame()
        self.empty_state.setObjectName("emptyStateCard")
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(22, 22, 22, 22)
        empty_layout.setSpacing(10)
        empty_title = QLabel("Ready when you are.")
        empty_title.setObjectName("emptyTitle")
        empty_text = QLabel(
            "Start with a scan. Klene will look for cleanup opportunities and explain everything before anything is removed."
        )
        empty_text.setObjectName("emptyText")
        empty_text.setWordWrap(True)
        steps = QLabel("1. Scan your system\n2. Preview selected cleanup\n3. Clean only what you confirm")
        steps.setObjectName("emptySteps")
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_text)
        empty_layout.addWidget(steps)

        self.section_tabs = QFrame()
        self.section_tabs.setObjectName("tabBar")
        tab_layout = QHBoxLayout(self.section_tabs)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(10)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_buttons: dict[str, QPushButton] = {}
        for index, section in enumerate(SECTION_ORDER):
            tab = QPushButton(SECTION_META[section][0])
            tab.setCheckable(True)
            tab.setObjectName("sectionTab")
            tab.setProperty("section", section)
            self.tab_group.addButton(tab, index)
            tab_layout.addWidget(tab)
            self.tab_buttons[section] = tab
        tab_layout.addStretch(1)

        self.section_stack = QStackedWidget()
        self.section_stack.setObjectName("sectionStack")
        self.section_pages: dict[str, QWidget] = {}
        self.section_grids: dict[str, QGridLayout] = {}
        for section in SECTION_ORDER:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(12)
            header = QFrame()
            header.setObjectName("sectionHeader")
            header.setProperty("section", section)
            header_layout = QVBoxLayout(header)
            header_layout.setContentsMargins(16, 14, 16, 14)
            header_layout.setSpacing(4)
            title = QLabel(SECTION_META[section][1])
            title.setObjectName("sectionHeaderTitle")
            subtitle = QLabel(SECTION_META[section][2])
            subtitle.setObjectName("sectionHeaderSubtitle")
            subtitle.setWordWrap(True)
            header_layout.addWidget(title)
            header_layout.addWidget(subtitle)

            grid_host = QWidget()
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(14)

            page_layout.addWidget(header)
            page_layout.addWidget(grid_host)
            page_layout.addStretch(1)
            self.section_stack.addWidget(page)
            self.section_pages[section] = page
            self.section_grids[section] = grid

        layout.addWidget(self.empty_state)
        layout.addWidget(self.section_tabs)
        layout.addWidget(self.section_stack, stretch=1)
        return frame

    def _build_action_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("actionPanel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        self.preview_button = QPushButton("Preview Selected")
        self.preview_button.setObjectName("secondaryAction")
        self.preview_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.clean_button = QPushButton("Clean Selected")
        self.clean_button.setObjectName("secondaryAction")
        self.clean_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))

        secondary = QHBoxLayout()
        secondary.setSpacing(10)
        self.about_button = QPushButton("About")
        self.about_button.setObjectName("ghostAction")
        self.about_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.activity_button = QToolButton()
        self.activity_button.setText("Activity Log")
        self.activity_button.setObjectName("ghostAction")
        self.activity_button.setCheckable(True)
        self.activity_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.activity_button.setArrowType(Qt.RightArrow)
        secondary.addWidget(self.about_button)
        secondary.addWidget(self.activity_button)

        layout.addWidget(self.preview_button)
        layout.addWidget(self.clean_button)
        layout.addStretch(1)
        layout.addLayout(secondary)
        return frame

    def _build_log_panel(self) -> QWidget:
        self.log_panel = QFrame()
        self.log_panel.setObjectName("logPanel")
        layout = QVBoxLayout(self.log_panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        title = QLabel("Activity Log")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("Mostly useful for troubleshooting and checking the last actions Klene took.")
        subtitle.setObjectName("sectionHeaderSubtitle")
        subtitle.setWordWrap(True)
        self.open_log_file_button = QPushButton("Open Log File")
        self.open_log_file_button.setObjectName("ghostAction")
        self.open_log_file_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Monospace"))
        self.log_output.setFixedHeight(150)
        self.log_output.setPlaceholderText("Activity details will appear here after a scan or preview.")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.open_log_file_button, alignment=Qt.AlignLeft)
        layout.addWidget(self.log_output)
        self.log_panel.hide()
        return self.log_panel

    def _wire_actions(self) -> None:
        self.scan_button.clicked.connect(self.start_scan)
        self.preview_button.clicked.connect(self.preview_cleanup)
        self.clean_button.clicked.connect(self.clean_selected)
        self.about_button.clicked.connect(self.show_about)
        self.activity_button.toggled.connect(self._toggle_activity_log)
        self.open_log_file_button.clicked.connect(self.open_logs)
        self.tab_group.buttonClicked.connect(self._change_section)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background-color: {THEME["background"]};
                color: {THEME["text"]};
            }}
            QLabel {{
                background: transparent;
            }}
            QMenuBar {{
                background-color: {THEME["background"]};
                color: {THEME["text"]};
            }}
            QMenuBar::item:selected, QMenu {{
                background-color: {THEME["panel"]};
            }}
            QFrame#heroPanel, QFrame#summaryPanel, QFrame#contentPanel, QFrame#actionPanel, QFrame#logPanel {{
                background: {THEME["panel"]};
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.03);
            }}
            QLabel#heroTitle {{
                font-size: 31px;
                font-weight: 700;
                color: {THEME["text"]};
            }}
            QLabel#heroSubtitle {{
                font-size: 15px;
                font-weight: 600;
                color: {THEME["muted_text"]};
            }}
            QLabel#heroSummary, QLabel#sectionHeaderSubtitle, QLabel#aboutSummary, QLabel#dialogIntro, QLabel#emptyText {{
                font-size: 13px;
                color: {THEME["muted_text"]};
            }}
            QLabel#heroStatus {{
                font-size: 14px;
                font-weight: 600;
                color: {THEME["text"]};
            }}
            QLabel#heroMeta, QLabel#aboutMeta {{
                font-size: 12px;
                color: {THEME["muted_text"]};
            }}
            QLabel#summaryTitle {{
                font-size: 21px;
                font-weight: 700;
                color: {THEME["text"]};
            }}
            QLabel#summaryDetail {{
                font-size: 13px;
                color: {THEME["muted_text"]};
            }}
            QFrame#metricChip {{
                background: {THEME["panel_alt"]};
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.04);
            }}
            QLabel#metricChipLabel {{
                font-size: 11px;
                color: {THEME["muted_text"]};
            }}
            QLabel#metricChipValue {{
                font-size: 18px;
                font-weight: 700;
                color: {THEME["text"]};
            }}
            QFrame#emptyStateCard {{
                background: {THEME["panel_alt"]};
                border-radius: 18px;
            }}
            QLabel#emptyTitle {{
                font-size: 24px;
                font-weight: 700;
                color: {THEME["text"]};
            }}
            QLabel#emptySteps {{
                font-size: 14px;
                line-height: 1.5;
                color: {THEME["text"]};
            }}
            QFrame#tabBar {{
                background: transparent;
                border: none;
            }}
            QPushButton#sectionTab {{
                background: {THEME["panel_soft"]};
                border: none;
                border-radius: 14px;
                padding: 12px 16px;
                color: {THEME["text"]};
                font-weight: 600;
            }}
            QPushButton#sectionTab:checked[section="recommended"] {{
                background: rgba(78, 199, 160, 0.18);
                color: {THEME["recommended"]};
            }}
            QPushButton#sectionTab:checked[section="review"] {{
                background: rgba(123, 196, 255, 0.18);
                color: {THEME["review"]};
            }}
            QPushButton#sectionTab:checked[section="advanced"] {{
                background: rgba(255, 178, 100, 0.18);
                color: {THEME["advanced"]};
            }}
            QFrame#sectionHeader {{
                border-radius: 18px;
                border: none;
            }}
            QFrame#sectionHeader[section="recommended"] {{
                background: rgba(78, 199, 160, 0.15);
            }}
            QFrame#sectionHeader[section="review"] {{
                background: rgba(123, 196, 255, 0.15);
            }}
            QFrame#sectionHeader[section="advanced"] {{
                background: rgba(255, 178, 100, 0.15);
            }}
            QLabel#sectionHeaderTitle, QLabel#sectionTitle {{
                font-size: 18px;
                font-weight: 700;
                color: {THEME["text"]};
            }}
            QFrame#targetCard {{
                background: {THEME["panel_alt"]};
                border-radius: 18px;
                border: 1px solid transparent;
            }}
            QFrame#targetCard[selected="true"][section="recommended"] {{
                background: rgba(78, 199, 160, 0.12);
                border: 1px solid rgba(78, 199, 160, 0.55);
            }}
            QFrame#targetCard[selected="true"][section="review"] {{
                background: rgba(123, 196, 255, 0.12);
                border: 1px solid rgba(123, 196, 255, 0.55);
            }}
            QFrame#targetCard[selected="true"][section="advanced"] {{
                background: rgba(255, 178, 100, 0.12);
                border: 1px solid rgba(255, 178, 100, 0.6);
            }}
            QLabel#cardTitle {{
                font-size: 16px;
                font-weight: 700;
                color: {THEME["text"]};
            }}
            QLabel#cardDescription, QLabel#whatHappens {{
                font-size: 13px;
                color: {THEME["muted_text"]};
            }}
            QLabel#metricCaption {{
                font-size: 11px;
                color: {THEME["muted_text"]};
            }}
            QLabel#metricValue {{
                font-size: 22px;
                font-weight: 700;
                color: {THEME["text"]};
            }}
            QLabel#statusText {{
                font-size: 14px;
                font-weight: 600;
                color: {THEME["text"]};
            }}
            QLabel#safetyBadge, QLabel#statusBadge {{
                border-radius: 11px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#safetyBadge[section="recommended"] {{
                background: rgba(78, 199, 160, 0.18);
                color: {THEME["recommended"]};
            }}
            QLabel#safetyBadge[section="review"] {{
                background: rgba(123, 196, 255, 0.18);
                color: {THEME["review"]};
            }}
            QLabel#safetyBadge[section="advanced"] {{
                background: rgba(255, 178, 100, 0.18);
                color: {THEME["advanced"]};
            }}
            QLabel#statusBadge[statusKind="ready"] {{
                background: rgba(105, 178, 255, 0.18);
                color: {THEME["primary"]};
            }}
            QLabel#statusBadge[statusKind="warning"] {{
                background: rgba(255, 210, 125, 0.18);
                color: {THEME["warning"]};
            }}
            QLabel#statusBadge[statusKind="clean"] {{
                background: rgba(114, 209, 174, 0.18);
                color: {THEME["success"]};
            }}
            QLabel#statusBadge[statusKind="unavailable"] {{
                background: rgba(159, 176, 196, 0.16);
                color: {THEME["muted_text"]};
            }}
            QPushButton, QToolButton {{
                background: {THEME["panel_soft"]};
                color: {THEME["text"]};
                border: none;
                border-radius: 14px;
                padding: 11px 16px;
                font-weight: 600;
            }}
            QPushButton:hover, QToolButton:hover {{
                background: #2c3b4f;
            }}
            QPushButton:disabled, QToolButton:disabled {{
                background: #232c39;
                color: #718293;
            }}
            QPushButton#primaryAction {{
                background: {THEME["primary"]};
                color: #122333;
            }}
            QPushButton#secondaryAction[mode="primary"] {{
                background: {THEME["primary"]};
                color: #122333;
            }}
            QPushButton#secondaryAction[mode="ready"] {{
                background: {THEME["panel_soft"]};
                color: {THEME["text"]};
            }}
            QPushButton#secondaryAction[mode="confirm"] {{
                background: {THEME["recommended"]};
                color: #10261f;
            }}
            QPushButton#ghostAction, QToolButton#ghostAction {{
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }}
            QDialog {{
                background: {THEME["background"]};
                color: {THEME["text"]};
            }}
            QLabel#aboutTitle {{
                font-size: 24px;
                font-weight: 700;
            }}
            QLabel#aboutSubtitle {{
                font-size: 14px;
                font-weight: 600;
                color: {THEME["muted_text"]};
            }}
            QPlainTextEdit#dialogDetails, QPlainTextEdit {{
                background: #0f1520;
                color: {THEME["text"]};
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }}
            """
        )

    def append_log(self, line: str) -> None:
        self.log_output.appendPlainText(line)

    def _toggle_activity_log(self, checked: bool) -> None:
        self.activity_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.log_panel.setVisible(checked)

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
        self.latest_targets = {target.key: target for target in getattr(report, "targets", [])}
        self.empty_state.hide()
        self.section_tabs.show()
        self.section_stack.show()

        for section in SECTION_ORDER:
            grid = self.section_grids[section]
            while grid.count():
                item = grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)

        for section in SECTION_ORDER:
            entries = [
                (key, self.latest_targets[key])
                for key, spec in CATEGORY_UI.items()
                if spec.section == section and key in self.latest_targets
            ]
            for index, (key, target) in enumerate(entries):
                row, col = divmod(index, 2)
                card = self.cards.get(key)
                if card is None:
                    card = TargetCard(key, CATEGORY_UI[key])
                    card.selection_changed.connect(self._selection_changed)
                    self.cards[key] = card
                card.update_target(target)
                self.section_grids[section].addWidget(card, row, col)

        self.tab_buttons["recommended"].setChecked(True)
        self._change_section(self.tab_buttons["recommended"])
        self._refresh_summary()

    def _change_section(self, button: QPushButton) -> None:
        section = button.property("section")
        self.section_stack.setCurrentWidget(self.section_pages[section])

    def selected_keys(self) -> list[str]:
        return [key for key, card in self.cards.items() if card.is_checked()]

    def _selection_changed(self) -> None:
        self.preview_ready = False
        self._refresh_summary()
        self._update_action_state()

    def _refresh_summary(self) -> None:
        selected_keys = self.selected_keys()
        selected_targets = [self.latest_targets[key] for key in selected_keys if key in self.latest_targets]
        selected_bytes = sum(target.estimated_bytes or 0 for target in selected_targets)
        review_selected = any(CATEGORY_UI[key].section == "review" for key in selected_keys)
        advanced_selected = any(CATEGORY_UI[key].section == "advanced" for key in selected_keys)

        if not self.scan_completed:
            self.summary_title.setText("Ready when you are.")
            self.summary_detail.setText(
                "Start with a scan. Klene will look for cleanup opportunities and explain everything before anything is removed."
            )
        else:
            if selected_keys:
                self.summary_title.setText(f"{format_bytes(selected_bytes)} selected from cleanup areas.")
            else:
                self.summary_title.setText("Scan complete. Choose the cleanup areas you want to review.")
            if advanced_selected:
                self.summary_detail.setText(
                    "Advanced items are selected. Klene will ask for extra confirmation before any package changes."
                )
            else:
                self.summary_detail.setText(
                    "Klene previews everything first. Nothing is removed until you confirm."
                )

        self.summary_size.value_widget.setText(format_bytes(selected_bytes))  # type: ignore[attr-defined]
        self.summary_count.value_widget.setText(str(len(selected_keys)))  # type: ignore[attr-defined]
        self.summary_review.value_widget.setText("Yes" if review_selected else "No")  # type: ignore[attr-defined]
        self.summary_advanced.value_widget.setText("Yes" if advanced_selected else "No")  # type: ignore[attr-defined]
        self.summary_safety.value_widget.setText("Preview required")  # type: ignore[attr-defined]

    def _update_action_state(self) -> None:
        has_selection = bool(self.selected_keys())
        self.preview_button.setEnabled(self.scan_completed and has_selection)
        self.clean_button.setEnabled(self.scan_completed and has_selection and self.preview_ready)

        self.preview_button.setProperty("mode", "primary" if self.scan_completed and has_selection else "ready")
        self.clean_button.setProperty("mode", "confirm" if self.preview_ready else "ready")
        for button in [self.preview_button, self.clean_button]:
            button.style().unpolish(button)
            button.style().polish(button)

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
            section_name = SECTION_META[CATEGORY_UI[key].section][1]
            grouped.setdefault(section_name, [])
            grouped[section_name].append(f"{CATEGORY_UI[key].title} • {format_bytes(target.estimated_bytes)}")
            grouped[section_name].append(
                f"  What happens: {shorten_home_paths(CATEGORY_UI[key].what_happens)}"
            )
            if target.preview:
                grouped[section_name].extend(
                    f"  - {format_display_path(line)}" for line in target.preview[:10]
                )
            else:
                grouped[section_name].append("  - No extra preview details were returned.")
            grouped[section_name].append("")

        lines = ["This is only a preview. Nothing has been removed.", ""]
        for section in SECTION_ORDER:
            section_name = SECTION_META[section][1]
            if section_name not in grouped:
                continue
            lines.append(section_name)
            lines.append("-" * len(section_name))
            lines.extend(grouped[section_name])
        self._run_worker("Preview", lambda: lines)

    def _show_preview(self, lines: object) -> None:
        preview = "\n".join(lines if isinstance(lines, list) else [])
        if not preview:
            preview = "Nothing is selected yet.\n\nChoose one or more cleanup areas, then preview again."
        self.append_log(preview)
        DetailDialog(
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

        if "orphans" in keys and not self._confirm_orphan_cleanup():
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
            title = CATEGORY_UI.get(result.key, CategoryUiSpec("", result.key, "", "", "", False)).title
            lines.append(f"{title}: {result.message}")
            if result.reclaimed_bytes:
                total_reclaimed += result.reclaimed_bytes
            if not result.success:
                failures.append(title)
        summary = (
            f"Cleanup finished. Estimated reclaimed space: {format_bytes(total_reclaimed)}."
            if total_reclaimed
            else "Cleanup finished."
        )
        if failures:
            summary = "Cleanup finished with a few issues. Review the details below."
        self.append_log(summary)
        self.append_log("\n".join(lines))
        DetailDialog(
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
