"""Read-only validation of SourceManifest identities and referenced bytes."""

import hashlib
from pathlib import Path

from cad_to_facts.contract import verify_source_manifest_identity
from cad_to_facts.domain.change import ManifestFile, SourceManifest
from cad_to_facts.domain.snapshot import Diagnostic
from cad_to_facts.errors import ConfigurationError


def _diagnostic(code: str, message: str, path: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity="error",
        stage="change",
        message=message,
        scope_refs=[path],
        affects=["change", "provenance"],
        impact="fatal",
        discovery_impact="none",
    )


def _validate_file(root: Path, item: ManifestFile, label: str) -> list[Diagnostic]:
    path = root / item.path
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return [
            _diagnostic(
                f"{label}_FILE_MISSING",
                f"Manifest file does not exist: {item.path}",
                item.path,
            )
        ]
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return [
            _diagnostic(
                f"{label}_FILE_INVALID",
                f"Manifest path is not a regular file inside its workspace: {item.path}",
                item.path,
            )
        ]
    digest = hashlib.sha256()
    size = 0
    with resolved.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    if size != item.size_bytes or digest.hexdigest() != item.sha256:
        return [
            _diagnostic(
                f"{label}_HASH_MISMATCH",
                f"Manifest file bytes do not match {item.path}",
                item.path,
            )
        ]
    return []


def validate_manifest_files(manifest: SourceManifest, directory: Path) -> list[Diagnostic]:
    """Validate a manifest and every referenced file without modifying anything."""

    diagnostics: list[Diagnostic] = []
    try:
        verify_source_manifest_identity(manifest)
    except ConfigurationError:
        diagnostics.append(
            _diagnostic(
                "MANIFEST_HASH_MISMATCH",
                "SourceManifest manifest_sha256 does not match its content",
                ".",
            )
        )
    root = Path(directory).resolve()
    for item in manifest.sources:
        diagnostics.extend(_validate_file(root, item, "SOURCE"))
    for item in manifest.dependency_files:
        diagnostics.extend(_validate_file(root, item, "DEPENDENCY"))
    source_paths = {item.path for item in manifest.sources}
    for item in manifest.generated_artifacts:
        diagnostics.extend(_validate_file(root, item, "GENERATED_ARTIFACT"))
        unknown_sources = sorted(set(item.source_paths) - source_paths)
        if unknown_sources:
            diagnostics.append(
                _diagnostic(
                    "ARTIFACT_SOURCE_MAPPING_UNKNOWN",
                    f"Generated artifact {item.path} references unknown source {unknown_sources[0]}",
                    item.path,
                )
            )
    return diagnostics
