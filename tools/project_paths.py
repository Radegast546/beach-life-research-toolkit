"""Shared repository and private-workspace paths for canonical project tools."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

LOCAL_ROOT_ENV = "BEACH_LIFE_LOCAL_ROOT"
LOCAL_ROOT_FILE = ".beach-life-local-root"


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Resolved repository-owned and machine-local project paths.

    When ``local_root`` equals ``repo_root``, properties retain the historical
    in-repository layout. An explicitly configured local root uses the external
    layout documented in ``PROJECT.md`` and never falls back to repository-local
    generated or proprietary data.
    """

    repo_root: Path
    local_root: Path

    @property
    def uses_external_root(self) -> bool:
        return self.local_root != self.repo_root

    # Repository-owned paths.
    @property
    def tools_dir(self) -> Path:
        return self.repo_root / "tools"

    @property
    def notes_dir(self) -> Path:
        return self.repo_root / "Notes"

    @property
    def remake_dir(self) -> Path:
        return self.repo_root / "Remake"

    @property
    def repo_assets_dir(self) -> Path:
        return self.remake_dir / "assets"

    @property
    def asset_manifest_path(self) -> Path:
        return self.repo_assets_dir / "asset_manifest.ron"

    @property
    def shaders_dir(self) -> Path:
        return self.repo_assets_dir / "shaders"

    @property
    def entity_rules_path(self) -> Path:
        return self.remake_dir / "src" / "data" / "entity_rules.tsv"

    @property
    def cargo_manifest_path(self) -> Path:
        return self.remake_dir / "Cargo.toml"

    # Local original inputs and runtime staging.
    @property
    def original_media_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "originals" / "media"
        return self.repo_root / "BeachLife_Original"

    @property
    def original_game_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "originals" / "game-input"
        return _legacy_original_game_dir(self.repo_root)

    @property
    def original_runtime_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "runtime" / "original-game"
        return self.original_game_dir

    @property
    def dxwnd_targets_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "runtime" / "dxwnd-targets"
        return self.original_game_dir / "_dxwnd"

    @property
    def support_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "support"
        return self.repo_root

    @property
    def dxwnd_dir(self) -> Path:
        if self.uses_external_root:
            return self.support_dir / "dxwnd"
        return self.repo_root / "DXWnd"

    @property
    def launcher_dir(self) -> Path:
        if self.uses_external_root:
            return self.support_dir / "launchers"
        return self.repo_root

    # Local extraction and generated caches.
    @property
    def extracted_data_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "cache" / "extracted-data"
        return self.repo_root / "extracted_data"

    @property
    def decrypted_ble_dir(self) -> Path:
        return self.extracted_data_dir / "ble"

    @property
    def extracted_sounds_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "cache" / "extracted-sounds"
        return self.repo_root / "extracted_sounds"

    @property
    def extracted_sprites_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "cache" / "extracted-sprites"
        return self.repo_root / "extracted_sprites"

    @property
    def runtime_assets_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "cache" / "remake-assets"
        return self.repo_assets_dir

    @property
    def audio_assets_dir(self) -> Path:
        return self.runtime_assets_dir / "audio"

    @property
    def map_assets_dir(self) -> Path:
        return self.runtime_assets_dir / "maps"

    @property
    def screen_assets_dir(self) -> Path:
        return self.runtime_assets_dir / "screens"

    @property
    def sprite_assets_dir(self) -> Path:
        return self.runtime_assets_dir / "sprites"

    @property
    def wateranim_assets_dir(self) -> Path:
        return self.runtime_assets_dir / "wateranims"

    @property
    def buildings_path(self) -> Path:
        return self.runtime_assets_dir / "buildings.ron"

    @property
    def map_exports_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "cache" / "map-exports"
        return self.repo_root / "Map_Exports"

    @property
    def screenshots_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "runtime" / "screenshots"
        return self.remake_dir / "screenshots"

    @property
    def analysis_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "analysis"
        return self.repo_root

    @property
    def ghidra_dir(self) -> Path:
        if self.uses_external_root:
            return self.analysis_dir / "ghidra"
        return self.repo_root / "GhidraProject.rep"

    @property
    def agent_runs_dir(self) -> Path:
        if self.uses_external_root:
            return self.analysis_dir / "agent-runs"
        return self.repo_root / ".agents"

    @property
    def scratch_dir(self) -> Path:
        if self.uses_external_root:
            return self.local_root / "scratch"
        return self.repo_root / "tmp"

    def local_relative(self, path: Path) -> str:
        """Return a stable forward-slash identifier below the local root."""
        return _relative_identifier(path, self.local_root, "local root")

    def repo_relative(self, path: Path) -> str:
        """Return a stable forward-slash identifier below the repository root."""
        return _relative_identifier(path, self.repo_root, "repository root")


def repo_root() -> Path:
    """Return the repository root based on this helper's location."""
    return Path(__file__).resolve().parents[1]


def local_root(
    *,
    repo: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the local workspace root without creating it."""
    resolved_repo = (repo or repo_root()).expanduser().resolve()
    environment = os.environ if environ is None else environ
    configured = environment.get(LOCAL_ROOT_ENV)
    if configured is not None:
        return _validate_configured_local_root(configured, resolved_repo)

    marker_path = resolved_repo / LOCAL_ROOT_FILE
    if not marker_path.exists():
        return resolved_repo
    try:
        configured = marker_path.read_text(encoding="utf-8")
    except OSError as error:
        raise OSError(f"failed to read local-root marker: {marker_path}") from error
    return _validate_configured_local_root(configured, resolved_repo)


def get_project_paths(
    *,
    repo: Path | None = None,
    local: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ProjectPaths:
    """Return all canonical paths with injectable values for deterministic tests."""
    resolved_repo = (repo or repo_root()).expanduser().resolve()
    if local is None:
        resolved_local = local_root(repo=resolved_repo, environ=environ)
    else:
        resolved_local = _validate_configured_local_root(str(local), resolved_repo)
    return ProjectPaths(repo_root=resolved_repo, local_root=resolved_local)


def original_game_dir(root: Path | None = None) -> Path:
    """Compatibility wrapper for the preferred original-game directory.

    An explicit ``root`` retains the historical behavior of checking directly
    below that path. With no argument, the configured project path contract is
    used.
    """
    if root is None:
        return get_project_paths().original_game_dir
    return _legacy_original_game_dir(Path(root).expanduser().resolve())


def require_path(path: Path, description: str) -> Path:
    """Return ``path`` or raise a clear ``FileNotFoundError``."""
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")
    return path


def _legacy_original_game_dir(root: Path) -> Path:
    preferred = root / "BeachLife_Original"
    legacy = root / "BeachLife_Remastered"
    if preferred.exists():
        return preferred
    if legacy.exists():
        return legacy
    return preferred


def _validate_configured_local_root(value: str, repo: Path) -> Path:
    configured = value.strip()
    if not configured:
        raise ValueError(f"{LOCAL_ROOT_ENV} must not be blank")

    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{LOCAL_ROOT_ENV} must be an absolute path: {candidate}")

    resolved = candidate.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"{LOCAL_ROOT_ENV} directory not found: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"{LOCAL_ROOT_ENV} is not a directory: {resolved}")
    if resolved == repo or resolved in repo.parents or repo in resolved.parents:
        raise ValueError(
            f"{LOCAL_ROOT_ENV} must be outside and disjoint from the repository: {resolved}"
        )
    return resolved


def _relative_identifier(path: Path, root: Path, description: str) -> str:
    resolved_path = path.expanduser().resolve()
    try:
        return resolved_path.relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"path is outside the {description}: {resolved_path}") from error
