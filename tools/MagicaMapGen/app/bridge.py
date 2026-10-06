"""Bridge to the mapgen core.

The GUI drives the generator through its CLI rather than importing it as a library.
That is deliberate: the CLI already carries meaningful exit codes (1 contract failed,
2 bad configuration, 3 runtime error, 4 schema violation) and the UI can map each onto
a distinct, actionable message. Importing the library would collapse all of them into
a traceback and lose the contract layer as a UI concept.

Generation runs in a QProcess so the window stays responsive; progress arrives as JSON
Lines written by ``mapgen --progress``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

EXIT_OK = 0
EXIT_CONTRACT = 1
EXIT_CONFIG = 2
EXIT_RUNTIME = 3
EXIT_SCHEMA = 4

EXIT_MEANING = {
    EXIT_OK: "Success - contract satisfied",
    EXIT_CONTRACT: "Contract failed - the map violates its theme guarantees",
    EXIT_CONFIG: "Configuration error - check the parameters",
    EXIT_RUNTIME: "Generation error",
    EXIT_SCHEMA: "Output failed map.schema.json validation",
}

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class MapSummary:
    """Everything the UI needs from one finished run, parsed from map.json."""
    path: Optional[Path] = None
    label: str = ""
    theme_id: str = ""
    seed: int = 0
    schema_version: int = 0
    generator_version: str = ""
    contract_passed: bool = False
    hard_failures: List[dict] = field(default_factory=list)
    warnings: List[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    legend: List[dict] = field(default_factory=list)
    grid: dict = field(default_factory=dict)
    instances: List[dict] = field(default_factory=list)
    height_source: str = ""

    @property
    def instance_count(self) -> int:
        return int(self.stats.get("instance_count", len(self.instances)))


def _run_cli(args: List[str], timeout: int = 30):
    return subprocess.run(
        [sys.executable, "-m", "mapgen"] + args,
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", timeout=timeout)

class MapgenBridge(QObject):
    """Runs one generation at a time and reports progress and completion."""

    progress = pyqtSignal(str, int)
    finished = pyqtSignal(int, object)
    log = pyqtSignal(str)

    def __init__(self, workdir: Path, parent=None):
        super().__init__(parent)
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._proc: Optional[QProcess] = None
        self._progress_path = self.workdir / ".progress.jsonl"
        self._out_dir = self.workdir

    @property
    def busy(self) -> bool:
        return self._proc is not None

    def list_themes(self) -> List[dict]:
        try:
            r = _run_cli(["--list-themes"])
            return json.loads(r.stdout) if r.returncode == 0 else []
        except Exception:
            return []

    def describe_theme(self, theme_id: str) -> Optional[dict]:
        try:
            r = _run_cli(["--describe-theme", theme_id])
            if r.returncode != 0:
                return None
            return json.loads(r.stdout)
        except Exception:
            return None

    def start(self, theme_id: str, seed: int, width: int, height: int,
              out_dir: Path, label: str = "",
              extra_args: Optional[List[str]] = None) -> None:
        if self.busy:
            self.log.emit("A generation is already running.")
            return

        self._out_dir = Path(out_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._progress_path.write_text("", encoding="utf-8")

        stem = label or f"{theme_id}_{seed}"
        args = [
            "-m", "mapgen",
            "--theme", theme_id,
            "--seed", str(seed),
            "--width", str(width),
            "--height", str(height),
            "--out", str(self._out_dir),
            "--label", stem,
            "--progress", str(self._progress_path),
            "--validate",
        ]
        for fmt in ("map", "csv", "pgm", "report"):
            args += ["--format", fmt]
        if extra_args:
            args += list(extra_args)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONPATH", str(REPO_ROOT))

        self.log.emit("python -m mapgen " + " ".join(args))
        proc = QProcess(self)
        proc.setWorkingDirectory(str(REPO_ROOT))
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        self._proc = proc
        proc.start(sys.executable, args)

    def start_with_config(self, config: dict, out_dir: Path,
                          label: str = "") -> Optional[Path]:
        """Write a mapgen config file and run it.

        Preferred over passing a dozen switches once the GUI can edit regions and
        category overrides, because mapgen's own config schema is then the contract
        instead of a parallel set of CLI conventions. The file is written next to the
        outputs so a run can always be reproduced by hand with
        ``python -m mapgen --config <file>``.
        """
        if self.busy:
            self.log.emit("A generation is already running.")
            return None

        self._out_dir = Path(out_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._progress_path.write_text("", encoding="utf-8")

        payload = dict(config)
        if label:
            payload["label"] = label
        payload.setdefault("formats", ["map", "csv", "pgm", "report"])

        config_path = self._out_dir / "ui_request.json"
        try:
            config_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.log.emit("Could not write config: %s" % exc)
            return None

        args = [
            "-m", "mapgen",
            "--config", str(config_path),
            "--out", str(self._out_dir),
            "--progress", str(self._progress_path),
            "--validate",
        ]
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONPATH", str(REPO_ROOT))

        self.log.emit("python -m mapgen " + " ".join(args))
        proc = QProcess(self)
        proc.setWorkingDirectory(str(REPO_ROOT))
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        self._proc = proc
        proc.start(sys.executable, args)
        return config_path

    def _on_output(self) -> None:
        proc = self._proc
        if proc is None:
            return
        chunk = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("[mapgen]"):
                self.log.emit(line)
        self._drain_progress()

    def _drain_progress(self) -> None:
        if not self._progress_path.exists():
            return
        try:
            lines = self._progress_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self.progress.emit(str(rec.get("stage", "")), int(rec.get("percent", 0)))

    def _on_finished(self, code: int, _status) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None:
            tail = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
            for line in tail.splitlines():
                if line.strip().startswith("[mapgen]"):
                    self.log.emit(line.strip())
        self._drain_progress()

        summary = None
        if code == EXIT_OK:
            summary = self._load_summary()
        self.finished.emit(code, summary)

    def _load_summary(self) -> Optional[MapSummary]:
        maps = sorted(self._out_dir.glob("*_map.json"))
        if not maps:
            self.log.emit("No map.json was produced.")
            return None
        path = maps[-1]
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.log.emit("Could not read %s: %s" % (path.name, exc))
            return None

        contract = doc.get("contract") or {}
        grid = doc.get("grid") or {}
        return MapSummary(
            path=path,
            label=doc.get("label", ""),
            theme_id=(doc.get("theme") or {}).get("id", ""),
            seed=int(doc.get("seed", 0)),
            schema_version=int(doc.get("schema_version", 0)),
            generator_version=doc.get("generator_version", ""),
            contract_passed=bool(contract.get("passed", False)),
            hard_failures=list(contract.get("hard_failures") or []),
            warnings=list(contract.get("warnings") or []),
            stats=dict(doc.get("stats") or {}),
            legend=list(grid.get("biome_legend") or []),
            grid=grid,
            instances=list(doc.get("instances") or []),
            height_source=grid.get("heightmap_raw_url", ""),
        )
