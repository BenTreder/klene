# Contributing

Thanks for your interest in Klene.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Arch package dependencies:

```bash
sudo pacman -S python pyside6 python-typer python-rich python-pytest pacman-contrib
```

## Development Workflow

- Keep cleanup behavior preview-first and safe by default.
- Do not add cleanup logic that skips confirmation for destructive actions.
- Avoid broad destructive commands such as `pacman -Scc` or blanket directory removal.
- Keep GUI and CLI behavior on the shared backend.

## Tests

Run these checks before opening a pull request:

```bash
python -m compileall src tests
PYTHONPATH=src python -m pytest
PYTHONPATH=src python -m klene --help
PYTHONPATH=src python -m klene doctor
```

## Safety Expectations

Klene is a cleanup utility. Small mistakes can delete the wrong data or remove the wrong packages.

- New cleanup targets must scan first.
- Real cleanup must require explicit confirmation.
- Package removal paths must remain especially conservative.
- If a change makes safety less obvious, document it clearly in the pull request.
