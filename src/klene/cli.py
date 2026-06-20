from __future__ import annotations

import json
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from klene.cleaner import (
    clean_all,
    clean_aur_cache,
    clean_flatpak_unused,
    clean_journal,
    clean_orphans,
    clean_pacman_cache,
    clean_thumbnails,
    clean_trash,
    clean_user_cache,
)
from klene.doctor import build_doctor_checks
from klene.logging_config import configure_logging
from klene.metadata import APP_NAME, APP_SUMMARY, APP_TAGLINE, APP_VERSION, AUTHOR_NAME, AUTHOR_WEBSITE
from klene.models import CleanupResult, ScanReport
from klene.platforms import get_provider
from klene.scanner import scan_system
from klene.safety import require_confirmation
from klene.utils import format_bytes

app = typer.Typer(help=f"{APP_NAME}: safe cleanup utility for Linux and Windows.")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"{APP_NAME} {APP_VERSION}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="Show Klene version information and exit.", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    configure_logging()


def _render_platform_header(report: ScanReport) -> None:
    if report.platform is None:
        return
    console.print(
        Panel.fit(
            f"{report.platform.platform_name}\nProvider: {report.platform.provider_name}\nSupport: {report.platform.support_label}\n{report.platform.status_message}",
            title="Detected Platform",
            border_style="cyan",
        )
    )


def _render_scan(report: ScanReport) -> None:
    _render_platform_header(report)
    table = Table(title="Klene Scan Report")
    table.add_column("Category")
    table.add_column("Group")
    table.add_column("Status")
    table.add_column("Estimated")
    table.add_column("Details")
    for target in report.targets:
        table.add_row(target.title, target.group.replace("_", " "), target.status.value, format_bytes(target.estimated_bytes), target.details)
    console.print(table)
    for note in report.notes:
        console.print(f"[yellow]{note}[/yellow]")


def _print_result(result: CleanupResult) -> None:
    color = "green" if result.success else "red"
    console.print(f"[{color}]{result.key}[/{color}]: {result.message}")
    if result.reclaimed_bytes is not None:
        console.print(f"Estimated reclaimable space: {format_bytes(result.reclaimed_bytes)}")
    for line in result.details:
        console.print(f"  - {line}")


def _confirm_execute(target: str, *, extra_warning: str | None = None) -> None:
    if extra_warning:
        console.print(f"[yellow]{extra_warning}[/yellow]")
    if not require_confirmation(f"Execute cleanup for {target}?"):
        raise typer.Abort()


def _dry_run_flag(execute: bool, dry_run: bool) -> bool:
    return False if execute else dry_run


def _selected_provider():
    return get_provider()


@app.command()
def scan(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output")] = False) -> None:
    report = scan_system()
    if json_output:
        console.print(json.dumps(report.to_dict(), indent=2))
        return
    _render_scan(report)


@app.command()
def gui() -> None:
    from klene.gui import launch_gui

    launch_gui()


@app.command()
def about() -> None:
    console.print(
        Panel.fit(
            f"{APP_NAME}\n{APP_TAGLINE}\nVersion {APP_VERSION}\nMade by {AUTHOR_NAME}\n{AUTHOR_WEBSITE}\n\n{APP_SUMMARY}",
            title="About",
            border_style="blue",
        )
    )


@app.command()
def platform() -> None:
    provider = _selected_provider()
    info = provider.get_platform_info()
    targets = provider.scan()
    available = ", ".join(target.title for target in targets) or "None"
    admin_required = ", ".join(target.title for target in targets if target.requires_admin) or "None"
    safety_notes = "\n".join(f"- {note}" for note in info.safety_notes) or "- None"
    console.print(
        Panel.fit(
            f"OS: {info.platform_name}\nProvider: {info.provider_name}\nSupport: {info.support_label}\nAvailable cleanup areas: {available}\nAdmin-needed areas: {admin_required}\nSafety notes:\n{safety_notes}",
            title="Klene Platform",
            border_style="green",
        )
    )


@app.command()
def doctor() -> None:
    checks = build_doctor_checks()
    table = Table(title="Klene Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")
    for check in checks:
        table.add_row(check.label, "[green]OK[/green]" if check.ok else "[yellow]Needs attention[/yellow]", check.detail)
    console.print(table)
    console.print(Panel.fit("Doctor mode only inspects your setup. It never deletes anything.", border_style="cyan"))


clean_app = typer.Typer(help="Cleanup commands")
app.add_typer(clean_app, name="clean")


@clean_app.command("list")
def clean_list() -> None:
    provider = _selected_provider()
    table = Table(title="Available Cleanup Areas")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Group")
    table.add_column("Can clean")
    for category in provider.get_category_definitions():
        table.add_row(category.id, category.title, category.group, "yes" if category.can_clean else "no")
    console.print(table)


@clean_app.command("pacman-cache")
def clean_pacman_cache_command(
    keep: Annotated[int, typer.Option("--keep", min=1)] = 3,
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("pacman cache")
    _print_result(clean_pacman_cache(keep=keep, dry_run=final_dry_run))


@clean_app.command("orphans")
def clean_orphans_command(
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("orphan packages", extra_warning="Package removal is destructive. Review the orphan list before continuing.")
        if not require_confirmation("Type yes again to confirm orphan removal."):
            raise typer.Abort()
    _print_result(clean_orphans(dry_run=final_dry_run))


@clean_app.command("journal")
def clean_journal_command(
    vacuum_time: Annotated[str, typer.Option("--vacuum-time")] = "14d",
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("system journal")
    _print_result(clean_journal(vacuum_time=vacuum_time, dry_run=final_dry_run))


@clean_app.command("user-cache")
def clean_user_cache_command(
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("user cache")
    _print_result(clean_user_cache(dry_run=final_dry_run))


@clean_app.command("trash")
def clean_trash_command(
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("trash")
    _print_result(clean_trash(dry_run=final_dry_run))


@clean_app.command("thumbnails")
def clean_thumbnails_command(
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("thumbnails")
    _print_result(clean_thumbnails(dry_run=final_dry_run))


@clean_app.command("aur-cache")
def clean_aur_cache_command(
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("AUR cache")
    _print_result(clean_aur_cache(dry_run=final_dry_run))


@clean_app.command("flatpak-cache")
def clean_flatpak_command(
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("Flatpak unused data")
    _print_result(clean_flatpak_unused(dry_run=final_dry_run))


@clean_app.command("all")
def clean_all_command(
    keep: Annotated[int, typer.Option("--keep", min=1)] = 3,
    vacuum_time: Annotated[str, typer.Option("--vacuum-time")] = "14d",
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Run the cleanup")] = False,
) -> None:
    final_dry_run = _dry_run_flag(execute, dry_run)
    if not final_dry_run:
        _confirm_execute("all selected cleanup tasks", extra_warning="This may require elevated privileges for some tasks.")
    for result in clean_all(keep=keep, vacuum_time=vacuum_time, dry_run=final_dry_run):
        _print_result(result)


def run() -> int:
    app()
    return 0


if __name__ == "__main__":
    sys.exit(run())
