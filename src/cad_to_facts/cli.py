import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cad_to_facts import __version__
from cad_to_facts.artifact import register
from cad_to_facts.bom import extract_bom
from cad_to_facts.contract import (
    bind_context,
    bind_requirement_bundle,
    bind_ruleset,
    bind_scope,
)
from cad_to_facts.domain.bom import BOMOptions
from cad_to_facts.domain.change import (
    ApprovalRecord,
    ChangePlan,
    ChangePreparationSpec,
    ChangeRequest,
    ExecutionRecord,
    SourceManifest,
    VerificationRequest,
)
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.domain.review import (
    Requirement,
    RequirementBundle,
    ReviewContext,
    ReviewRequest,
    ReviewReport,
    ReviewScope,
    RuleSet,
)
from cad_to_facts.domain.view import (
    RenderOutput,
    RendererInfo,
    TargetSelector,
    ViewRenderManifest,
    ViewSpecification,
)
from cad_to_facts.drawing_output import select_entities, snapshot_summary
from cad_to_facts.prepare import prepare_change
from cad_to_facts.review import review, select_rules
from cad_to_facts.verification import verify_change


def read(*args, **kwargs):
    # Keep doctor usable when a native geometry dependency is damaged.
    from cad_to_facts.snapshot import read as read_snapshot

    return read_snapshot(*args, **kwargs)


def extract(*args, **kwargs):
    from cad_to_facts.facts import extract as extract_facts

    return extract_facts(*args, **kwargs)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(json.dumps({"error": {"category": "configuration_or_input", "message": message}}))
        raise SystemExit(2)


def _load_object(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _requirements(path: str) -> RequirementBundle:
    values = _load_object(path).get("requirements")
    if not values:
        raise ValueError("RequirementBundle must contain at least one requirement")
    bundle = RequirementBundle(
        bundle_id="0" * 64,
        requirements=[Requirement(content_hash="0" * 64, **value) for value in values],
    )
    return bind_requirement_bundle(bundle)


def _ruleset(path: str, bundle: RequirementBundle) -> RuleSet:
    value = _load_object(path)
    ruleset = RuleSet(
        ruleset_id="0" * 64,
        version=value["version"],
        requirement_bundle=bundle,
        rules=value["rules"],
    )
    return bind_ruleset(ruleset)


def _scope(path: str) -> ReviewScope:
    return bind_scope(ReviewScope(scope_id="0" * 64, **_load_object(path)))


def _context(path: str) -> ReviewContext:
    return bind_context(ReviewContext(context_id="0" * 64, **_load_object(path)))


def _query_for(snapshot, ruleset: RuleSet, scope: ReviewScope) -> ExtractionQuery:
    requests: dict[tuple[str, str, str], FactRequest] = {}
    scope_kinds = {selector.entity_kind for selector in scope.subject_selectors}
    selected = select_rules(ruleset, scope)
    for rule in selected:
        predicates = [(item.name, item.predicate) for item in rule.inputs]
        applicability_predicate = rule.applicability.get("fact_predicate")
        if applicability_predicate:
            predicates.append(("applicability", applicability_predicate))
        for entity in snapshot.entities:
            if entity.entity_kind != rule.subject_selector.entity_kind or entity.entity_kind not in scope_kinds:
                continue
            for name, predicate in predicates:
                request = FactRequest(name=name, predicate=predicate, subject_id=entity.entity_id)
                requests[(request.name, request.predicate, request.subject_id)] = request
    for item in scope.required_inputs:
        if item.subject_id == "*":
            subjects = [
                entity for entity in snapshot.entities if entity.entity_kind in scope_kinds
            ]
        else:
            subjects = [entity for entity in snapshot.entities if entity.entity_id == item.subject_id]
        for entity in subjects:
            request = item.model_copy(update={"subject_id": entity.entity_id})
            requests[(request.name, request.predicate, request.subject_id)] = request
    return ExtractionQuery(requests=list(requests.values()))


def _read_options(args: argparse.Namespace) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if getattr(args, "read_scope", None):
        options["read_scope"] = args.read_scope
    if getattr(args, "oda_path", None):
        options["oda_executable"] = args.oda_path
    if getattr(args, "xref_mode", None):
        options["xref_mode"] = args.xref_mode
    if getattr(args, "xref_root", None) is not None:
        options["xref_roots"] = args.xref_root
    for argument, option in (
        ("xref_max_depth", "xref_max_depth"),
        ("xref_max_files", "xref_max_files"),
        ("xref_max_bytes", "xref_max_bytes"),
        ("xref_timeout_seconds", "xref_timeout_seconds"),
    ):
        value = getattr(args, argument, None)
        if value is not None:
            options[option] = value
    return options


def _review(args: argparse.Namespace) -> int:
    artifact = register(args.file)
    snapshot = read(artifact, _read_options(args))
    bundle = _requirements(args.requirements)
    ruleset = _ruleset(args.rules, bundle)
    scope = _scope(args.scope)
    factset = extract(snapshot, _query_for(snapshot, ruleset, scope))
    request = ReviewRequest(
        snapshot=snapshot,
        factset=factset,
        ruleset=ruleset,
        scope=scope,
        context=_context(args.context),
        reviewer_version=__version__,
    )
    report = review(request)
    print(report.model_dump_json())
    return 3 if report.tool_error else 0


def _inspect(args: argparse.Namespace) -> int:
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")
    artifact = register(args.file)
    snapshot = read(artifact, _read_options(args))
    if args.summary:
        print(json.dumps(
            {"artifact": artifact.model_dump(mode="json"), "snapshot": snapshot_summary(snapshot)},
            ensure_ascii=False,
        ))
        return 0
    entities = snapshot.entities[: args.limit]
    truncated = len(entities) < len(snapshot.entities)
    if snapshot.drawing is not None:
        from cad_to_facts.drawing_facts import default_requests

        query = default_requests(snapshot, entities)
    else:
        predicates = ["volume", "area", "bbox.extent.x", "bbox.extent.y", "bbox.extent.z"]
        query = ExtractionQuery(
            requests=[
                FactRequest(name=f"{entity.entity_id}:{predicate}", predicate=predicate, subject_id=entity.entity_id)
                for entity in entities
                for predicate in predicates
            ]
        )
    factset = extract(snapshot, query)
    output = {
        "artifact": artifact.model_dump(mode="json"),
        "snapshot": snapshot.model_dump(mode="json"),
        "factset": factset.model_dump(mode="json"),
        "selection": {
            "entity_total": len(snapshot.entities),
            "entities_returned": len(entities),
            "truncated": truncated,
            "next_cursor": snapshot.entities[len(entities)].entity_id if truncated else None,
        },
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def _query(args: argparse.Namespace) -> int:
    artifact = register(args.file)
    snapshot = read(artifact, _read_options(args))
    entities, selection = select_entities(
        snapshot,
        kinds=args.kind,
        layers=args.layer,
        containers=args.container,
        text=args.text,
        cursor=args.cursor,
        limit=args.limit,
    )
    from cad_to_facts.drawing_facts import default_requests

    factset = extract(snapshot, default_requests(snapshot, entities))
    output = {
        "artifact": artifact.model_dump(mode="json"),
        "snapshot": snapshot_summary(snapshot),
        "entities": [item.model_dump(mode="json") for item in entities],
        "factset": factset.model_dump(mode="json"),
        "selection": selection,
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def _resolve(args: argparse.Namespace) -> int:
    from cad_to_facts.resolution import resolve_target

    artifact = register(args.file)
    if artifact.format != "step":
        raise ValueError("resolve currently requires a STEP artifact")
    snapshot = read(artifact, {"read_scope": "assembly"})
    resolution = resolve_target(
        snapshot, TargetSelector.model_validate(_load_object(args.selector))
    )
    print(json.dumps({
        "artifact": artifact.model_dump(mode="json"),
        "snapshot": snapshot_summary(snapshot),
        "resolution": resolution.model_dump(mode="json"),
    }, ensure_ascii=False))
    return 0


def _features(args: argparse.Namespace) -> int:
    from cad_to_facts.domain.feature import FeatureQuery
    from cad_to_facts.features import recognize_features

    artifact = register(args.file)
    if artifact.format != "step":
        raise ValueError("features currently requires a STEP artifact")
    snapshot = read(artifact, {"read_scope": "assembly"})
    query = (
        FeatureQuery.model_validate(_load_object(args.query))
        if args.query
        else FeatureQuery(kinds=["door", "window", "hole"])
    )
    report = recognize_features(snapshot, query)
    print(json.dumps({
        "artifact": artifact.model_dump(mode="json"),
        "snapshot": snapshot_summary(snapshot),
        "features": report.model_dump(mode="json"),
    }, ensure_ascii=False))
    return 0


def _orient(args: argparse.Namespace) -> int:
    from cad_to_facts.domain.orientation import OrientationPolicy
    from cad_to_facts.orientation import infer_orientation

    artifact = register(args.file)
    if artifact.format != "step":
        raise ValueError("orient currently requires a STEP artifact")
    snapshot = read(artifact, {"read_scope": "assembly"})
    policy = (
        OrientationPolicy.model_validate(_load_object(args.policy))
        if args.policy else OrientationPolicy()
    )
    report = infer_orientation(
        snapshot,
        TargetSelector.model_validate(_load_object(args.selector)),
        policy,
    )
    print(json.dumps({
        "artifact": artifact.model_dump(mode="json"),
        "snapshot": snapshot_summary(snapshot),
        "orientation": report.model_dump(mode="json"),
    }, ensure_ascii=False))
    return 0


def _ask(args: argparse.Namespace) -> int:
    artifact = register(args.file)
    if artifact.format == "step":
        from cad_to_facts.domain.question import QuestionSpec
        from cad_to_facts.question import answer_question
        from cad_to_facts.question_language import parse_question

        snapshot = read(artifact, {"read_scope": "assembly"})
        spec = (
            QuestionSpec.model_validate(_load_object(args.spec))
            if args.spec else parse_question(args.question)
        )
        report = answer_question(snapshot, spec)
    elif artifact.format in {"dxf", "dwg"}:
        from cad_to_facts.domain.drawing_question import DrawingQuestionSpec
        from cad_to_facts.drawing_question import answer_drawing_question

        if args.spec is None:
            raise ValueError(
                "drawing questions require an explicit DrawingQuestionSpec; "
                "the bounded natural-language grammar is STEP-only"
            )
        snapshot = read(artifact, _read_options(args))
        spec = DrawingQuestionSpec.model_validate(_load_object(args.spec))
        report = answer_drawing_question(snapshot, spec)
    else:
        raise ValueError(f"ask does not support artifact format {artifact.format!r}")
    print(json.dumps({
        "artifact": artifact.model_dump(mode="json"),
        "snapshot": snapshot_summary(snapshot),
        "answer": report.model_dump(mode="json"),
    }, ensure_ascii=False))
    return 0


def _render_step(args: argparse.Namespace, artifact, output_path: Path) -> int:
    from cad_to_facts.identity import structured_hash
    from cad_to_facts.model_render import render_step_svg

    if not args.target or not args.view_spec:
        raise ValueError("STEP render requires both --target and --view-spec")
    if output_path.suffix.casefold() != ".svg":
        raise ValueError("STEP render currently supports only .svg output")
    manifest_path = output_path.with_suffix(".view.json")
    for path in (output_path, manifest_path):
        if path == Path(artifact.source_locator):
            raise ValueError("Render outputs must be new files, not the source artifact")
        if path.exists():
            raise ValueError(f"Render output already exists: {path}")
    snapshot = read(artifact, {"read_scope": "assembly"})
    view = ViewSpecification.model_validate(_load_object(args.view_spec))
    svg, target, stats, diagnostics = render_step_svg(snapshot, args.target, view)
    content = svg.encode("utf-8")
    output = RenderOutput(
        path=str(output_path),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )
    manifest = ViewRenderManifest(
        view_render_id="0" * 64,
        artifact_sha256=artifact.sha256,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        target=target,
        view=view,
        renderer=RendererInfo(kernel_version=snapshot.parser_kernel_version),
        render=stats,
        output=output,
        diagnostics=diagnostics,
    )
    manifest = manifest.model_copy(update={
        "view_render_id": structured_hash(
            "step-view-render", manifest, exclude={"view_render_id"}
        )
    })
    manifest_content = (manifest.model_dump_json(indent=2) + "\n").encode("utf-8")
    created = []
    try:
        with output_path.open("xb") as stream:
            created.append(output_path)
            stream.write(content)
        with manifest_path.open("xb") as stream:
            created.append(manifest_path)
            stream.write(manifest_content)
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        raise
    print(json.dumps({
        "artifact": artifact.model_dump(mode="json"),
        "snapshot_id": snapshot.snapshot_id,
        "view_render": manifest.model_dump(mode="json"),
        "manifest_path": str(manifest_path),
    }, ensure_ascii=False))
    return 0


def _render(args: argparse.Namespace) -> int:
    artifact = register(args.file)
    output_path = Path(args.output).resolve()
    if artifact.format == "step":
        return _render_step(args, artifact, output_path)
    if args.target or args.view_spec:
        raise ValueError("--target and --view-spec are valid only for STEP render")
    from cad_to_facts.drawing_render import render_svg

    if output_path == Path(artifact.source_locator):
        raise ValueError("Render output must be a new file, not the source artifact")
    snapshot = read(artifact, _read_options(args))
    svg = render_svg(snapshot, args.layout).encode("utf-8")
    # Exclusive creation makes rendered work products immutable by default.
    with output_path.open("xb") as stream:
        stream.write(svg)
    print(json.dumps({
        "artifact": artifact.model_dump(mode="json"),
        "snapshot_id": snapshot.snapshot_id,
        "output": {
            "path": str(output_path),
            "format": "svg",
            "layout": args.layout,
            "sha256": hashlib.sha256(svg).hexdigest(),
            "size_bytes": len(svg),
        },
        "diagnostics": [item.model_dump(mode="json") for item in snapshot.diagnostics],
        "fidelity": "review_render_only_not_visual_or_geometric_equivalence",
    }, ensure_ascii=False))
    return 0


def _drawing_bom(args: argparse.Namespace) -> int:
    from cad_to_facts.domain.drawing_bom import DrawingBOMOptions
    from cad_to_facts.drawing_bom import extract_drawing_bom

    artifact = register(args.file)
    snapshot = read(artifact, _read_options(args))
    bom = extract_drawing_bom(snapshot, DrawingBOMOptions(
        part_tag=args.part_tag,
        quantity_tag=args.quantity_tag,
        material_tag=args.material_tag,
        description_tag=args.description_tag,
        required_tags=args.require_tag,
        containers=args.container or ["Model"],
        allow_external_reference_exclusion=args.allow_xref_exclusion,
    ))
    print(bom.model_dump_json())
    return 0


def _bom(args: argparse.Namespace) -> int:
    artifact = register(args.file)
    snapshot = read(artifact, {"read_scope": "assembly"})
    bom = extract_bom(
        snapshot, BOMOptions(required_properties=list(args.require_property))
    )
    print(bom.model_dump_json(exclude_none=True))
    return 0


def _process_input(args: argparse.Namespace) -> int:
    from cad_to_facts.domain.process import ProcessInputOptions
    from cad_to_facts.process import prepare

    artifact = register(args.file)
    if artifact.format != "step":
        raise ValueError("process-input currently requires a STEP artifact")
    snapshot = read(artifact, {"read_scope": "single_part"})
    predicates = ["volume", "area", "bbox.extent.x", "bbox.extent.y", "bbox.extent.z"]
    factset = extract(snapshot, ExtractionQuery(requests=[
        FactRequest(
            name=f"{entity.entity_id}:{predicate}",
            predicate=predicate,
            subject_id=entity.entity_id,
        )
        for entity in snapshot.entities
        for predicate in predicates
    ]))
    context = (
        _context(args.context)
        if args.context
        else bind_context(ReviewContext(context_id="0" * 64, values={}))
    )
    option_values: dict[str, Any] = {"required_design_inputs": args.require_design_input}
    if args.require_context is not None:
        option_values["required_context"] = args.require_context
    result = prepare(
        snapshot,
        factset,
        context,
        ProcessInputOptions(**option_values),
    )
    print(result.model_dump_json())
    return 0


def _pmi(args: argparse.Namespace) -> int:
    from cad_to_facts.pmi import extract_pmi

    artifact = register(args.file)
    snapshot = read(artifact, _read_options(args))
    result = extract_pmi(artifact, snapshot)
    output = {
        "artifact": artifact.model_dump(mode="json"),
        "snapshot": snapshot_summary(snapshot),
        "pmi": result.model_dump(mode="json"),
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def _doctor(args: argparse.Namespace) -> int:
    from cad_to_facts.doctor import run_checks

    report = run_checks(args.oda_path)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


def _optional_model(path: str | None, model):
    return model.model_validate(_load_object(path)) if path else None


def _facts_for_profile(snapshot, profile):
    return extract(
        snapshot,
        ExtractionQuery(
            requests=[
                item.model_copy(update={"subject_id": entity.entity_id})
                for entity in snapshot.entities
                for item in profile.extraction_query_template.requests
            ]
        ),
    )


def _prepare_change_command(args: argparse.Namespace) -> int:
    artifact = register(args.before)
    snapshot = read(artifact, _read_options(args))
    bundle = _requirements(args.requirements)
    ruleset = _ruleset(args.rules, bundle)
    scope = _scope(args.scope)
    context = _context(args.context)
    origin_factset = extract(snapshot, _query_for(snapshot, ruleset, scope))
    manifest_path = Path(args.before_manifest).resolve() if args.before_manifest else None
    preparation = prepare_change(
        snapshot=snapshot,
        origin_factset=origin_factset,
        origin_report=ReviewReport.model_validate(_load_object(args.report)),
        ruleset=ruleset,
        scope=scope,
        context=context,
        reviewer_version=__version__,
        finding_id=args.finding,
        spec=ChangePreparationSpec.model_validate(_load_object(args.spec)),
        before_manifest=_optional_model(args.before_manifest, SourceManifest),
        before_manifest_directory=str(manifest_path.parent) if manifest_path else None,
    )
    print(preparation.model_dump_json(exclude_none=True))
    return 0


def _verify_change_command(args: argparse.Namespace) -> int:
    change = ChangeRequest.model_validate(_load_object(args.request))
    before_artifact = register(args.before)
    after_artifact = register(args.after) if Path(args.after).exists() else None
    before_snapshot = read(
        before_artifact, change.verification_profile.parse_options
    )
    after_snapshot = (
        read(after_artifact, change.verification_profile.parse_options)
        if after_artifact
        else None
    )
    before_factset = _facts_for_profile(before_snapshot, change.verification_profile)
    after_factset = (
        _facts_for_profile(after_snapshot, change.verification_profile)
        if after_snapshot
        else None
    )
    before_manifest_path = Path(args.before_manifest).resolve() if args.before_manifest else None
    after_manifest_path = Path(args.after_manifest).resolve() if args.after_manifest else None
    report = verify_change(
        VerificationRequest(
            change=change,
            plan=_optional_model(args.plan, ChangePlan),
            approval=_optional_model(args.approval, ApprovalRecord),
            execution=_optional_model(args.execution, ExecutionRecord),
            before_artifact=before_artifact,
            after_artifact=after_artifact,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            before_factset=before_factset,
            after_factset=after_factset,
            before_manifest=_optional_model(args.before_manifest, SourceManifest),
            after_manifest=_optional_model(args.after_manifest, SourceManifest),
            before_manifest_directory=(
                str(before_manifest_path.parent) if before_manifest_path else None
            ),
            after_manifest_directory=(
                str(after_manifest_path.parent) if after_manifest_path else None
            ),
            origin_review=_optional_model(args.origin_review, ReviewReport),
            allow_relocated_output=args.replay_relocated_output,
        )
    )
    print(report.model_dump_json(exclude_none=True))
    return 3 if report.tool_error else 0


def _add_xref_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--xref-mode",
        choices=["unresolved", "linked", "flatten"],
        help="XREF handling: unresolved (default), independent linked records, or source-tagged flattening",
    )
    parser.add_argument(
        "--xref-root",
        action="append",
        help="Allowed local XREF directory (repeatable; required for resolution)",
    )
    parser.add_argument("--xref-max-depth", type=int, help="Maximum nested XREF depth (default: 8)")
    parser.add_argument("--xref-max-files", type=int, help="Maximum XREF files loaded (default: 64)")
    parser.add_argument("--xref-max-bytes", type=int, help="Maximum total XREF source bytes (default: 268435456)")
    parser.add_argument("--xref-timeout-seconds", type=float, help="Total XREF resolution timeout (default: 120)")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="facts", description="Traceable CAD facts and deterministic review")
    subcommands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subcommands.add_parser(
        "inspect", help="Inspect a STEP model or DWG/DXF drawing and extract selective facts"
    )
    inspect_parser.add_argument("file")
    inspect_parser.add_argument(
        "--oda-path",
        help="Required ODAFileConverter executable path for DWG input; DXF and STEP do not use it",
    )
    inspect_parser.add_argument(
        "--read-scope", choices=["single_part", "assembly", "drawing"], default=None
    )
    inspect_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of entities selected for fact extraction (default: 20)",
    )
    inspect_parser.add_argument(
        "--summary",
        action="store_true",
        help="Return counts and drawing structure summaries without the entity catalog or facts",
    )
    _add_xref_arguments(inspect_parser)
    inspect_parser.set_defaults(handler=_inspect)
    query_parser = subcommands.add_parser(
        "query", help="Select and paginate drawing entities without dumping the full catalog"
    )
    query_parser.add_argument("file")
    query_parser.add_argument("--oda-path", help="Required ODAFileConverter path for DWG input")
    query_parser.add_argument(
        "--read-scope", choices=["drawing"], default=None, help=argparse.SUPPRESS
    )
    query_parser.add_argument("--kind", action="append", default=[], help="DXF entity kind filter (repeatable)")
    query_parser.add_argument("--layer", action="append", default=[], help="Exact layer filter (repeatable)")
    query_parser.add_argument("--container", action="append", default=[], help="Exact layout/block container filter (repeatable)")
    query_parser.add_argument("--text", help="Case-sensitive substring of TEXT/MTEXT/ATTRIB/ATTDEF content")
    query_parser.add_argument("--cursor", help="Snapshot-local entity cursor returned by a previous page")
    query_parser.add_argument("--limit", type=int, default=20, help="Maximum entities returned (default: 20)")
    _add_xref_arguments(query_parser)
    query_parser.set_defaults(handler=_query)
    resolve_parser = subcommands.add_parser(
        "resolve", help="Resolve STEP occurrence candidates without guessing among ambiguous matches"
    )
    resolve_parser.add_argument("file")
    resolve_parser.add_argument(
        "--selector", required=True, help="TargetSelector JSON; all supplied constraints are ANDed"
    )
    resolve_parser.set_defaults(handler=_resolve)
    features_parser = subcommands.add_parser(
        "features", help="Report bounded door/window candidates and conservative cylindrical through holes"
    )
    features_parser.add_argument("file")
    features_parser.add_argument("--query", help="FeatureQuery JSON; default: door/window/hole")
    features_parser.set_defaults(handler=_features)
    orient_parser = subcommands.add_parser(
        "orient", help="Infer an explicitly assumed front from bounded bounding-box heuristics"
    )
    orient_parser.add_argument("file")
    orient_parser.add_argument("--selector", required=True, help="TargetSelector JSON")
    orient_parser.add_argument("--policy", help="OrientationPolicy JSON with explicit tolerances")
    orient_parser.set_defaults(handler=_orient)
    ask_parser = subcommands.add_parser(
        "ask", help="Answer bounded STEP questions or an explicit DrawingQuestionSpec"
    )
    ask_parser.add_argument("file")
    ask_input = ask_parser.add_mutually_exclusive_group(required=True)
    ask_input.add_argument(
        "--spec", help="Explicit QuestionSpec (STEP) or DrawingQuestionSpec (DXF/DWG) JSON"
    )
    ask_input.add_argument(
        "--question",
        help="Bounded offline STEP Chinese/English grammar; drawing questions require --spec",
    )
    ask_parser.add_argument("--oda-path", help="Required ODAFileConverter path for DWG input")
    ask_parser.add_argument(
        "--read-scope", choices=["drawing"], default=None, help=argparse.SUPPRESS
    )
    _add_xref_arguments(ask_parser)
    ask_parser.set_defaults(handler=_ask)
    render_parser = subcommands.add_parser(
        "render", help="Render a drawing layout or one resolved STEP occurrence to a new SVG"
    )
    render_parser.add_argument("file")
    render_parser.add_argument("--output", required=True, help="New SVG path; existing files are never overwritten")
    render_parser.add_argument("--layout", default="Model", help="Drawing layout name (default: Model)")
    render_parser.add_argument("--target", help="STEP occurrence:N selected by facts resolve")
    render_parser.add_argument("--view-spec", help="STEP ViewSpecification JSON")
    render_parser.add_argument("--oda-path", help="Required ODAFileConverter path for DWG input")
    render_parser.add_argument("--read-scope", choices=["drawing"], default=None, help=argparse.SUPPRESS)
    _add_xref_arguments(render_parser)
    render_parser.set_defaults(handler=_render)
    drawing_bom_parser = subcommands.add_parser(
        "drawing-bom", help="Extract a neutral BOM from explicitly configured block attributes"
    )
    drawing_bom_parser.add_argument("file")
    drawing_bom_parser.add_argument("--part-tag", required=True, help="ATTRIB tag containing the part number")
    drawing_bom_parser.add_argument("--quantity-tag", help="Optional ATTRIB tag containing a positive integer quantity")
    drawing_bom_parser.add_argument("--material-tag", help="Optional ATTRIB tag to retain as material")
    drawing_bom_parser.add_argument("--description-tag", help="Optional ATTRIB tag to retain as description")
    drawing_bom_parser.add_argument("--require-tag", action="append", default=[], help="Additional required ATTRIB tag (repeatable)")
    drawing_bom_parser.add_argument("--container", action="append", default=None, help="Layout/block container to count (default: Model; repeatable)")
    drawing_bom_parser.add_argument(
        "--allow-xref-exclusion",
        action="store_true",
        help="Explicitly accept that configured BOM scope omits external-reference occurrences",
    )
    drawing_bom_parser.add_argument("--oda-path", help="Required ODAFileConverter path for DWG input")
    drawing_bom_parser.add_argument("--read-scope", choices=["drawing"], default=None, help=argparse.SUPPRESS)
    _add_xref_arguments(drawing_bom_parser)
    drawing_bom_parser.set_defaults(handler=_drawing_bom)
    bom_parser = subcommands.add_parser(
        "bom", help="Extract neutral BOM rows from STEP assembly structure"
    )
    bom_parser.add_argument("file")
    bom_parser.add_argument(
        "--require-property",
        action="append",
        default=[],
        help="Declared property required for completeness (repeatable; currently name)",
    )
    bom_parser.set_defaults(handler=_bom)
    process_parser = subcommands.add_parser(
        "process-input",
        help="Prepare neutral single-part process inputs without planning operations",
    )
    process_parser.add_argument("file")
    process_parser.add_argument("--context", help="Optional JSON object with a values object")
    process_parser.add_argument(
        "--require-context",
        action="append",
        default=None,
        help="Required user-context key (repeatable; default: material, stock, batch_size)",
    )
    process_parser.add_argument(
        "--require-design-input",
        action="append",
        default=[],
        choices=["declared_material", "semantic_pmi", "validated_features"],
        help="Design-side input that must be available (repeatable)",
    )
    process_parser.set_defaults(handler=_process_input)
    pmi_parser = subcommands.add_parser(
        "pmi", help="Extract declared AP242 semantic PMI without inferring missing annotations"
    )
    pmi_parser.add_argument("file")
    pmi_parser.add_argument(
        "--read-scope",
        choices=["single_part", "assembly"],
        default=None,
        help="Snapshot profile used to bind PMI geometry links (default: single_part)",
    )
    pmi_parser.set_defaults(handler=_pmi)
    doctor_parser = subcommands.add_parser(
        "doctor", help="Check the active Python environment without parsing CAD or running converters"
    )
    doctor_parser.add_argument(
        "--check", action="store_true", required=True, help="Run local installation diagnostics"
    )
    doctor_parser.add_argument(
        "--oda-path", help="Optional explicit ODA file to hash and validate; never discovered automatically"
    )
    doctor_parser.set_defaults(handler=_doctor)
    review_parser = subcommands.add_parser(
        "review", help="Review a STEP model or DWG/DXF drawing against explicit JSON contracts"
    )
    review_parser.add_argument("file")
    review_parser.add_argument(
        "--oda-path",
        help="Required ODAFileConverter executable path for DWG input; DXF and STEP do not use it",
    )
    review_parser.add_argument(
        "--read-scope", choices=["single_part", "assembly", "drawing"], default=None
    )
    review_parser.add_argument("--requirements", required=True, help="RequirementBundle JSON")
    review_parser.add_argument("--rules", required=True, help="RuleSet rules JSON")
    review_parser.add_argument("--scope", required=True, help="ReviewScope JSON")
    review_parser.add_argument("--context", required=True, help="ReviewContext JSON")
    _add_xref_arguments(review_parser)
    review_parser.set_defaults(handler=_review)
    prepare_parser = subcommands.add_parser(
        "prepare-change",
        help="Derive a ChangeRequest and external handoff ChangePlan without executing CAD",
    )
    prepare_parser.add_argument("--report", required=True, help="Original ReviewReport JSON")
    prepare_parser.add_argument("--finding", required=True, help="Violated or unknown finding ID")
    prepare_parser.add_argument("--before", required=True, help="Baseline STEP file")
    prepare_parser.add_argument(
        "--read-scope", choices=["single_part", "assembly", "drawing"], default=None
    )
    prepare_parser.add_argument("--requirements", required=True, help="RequirementBundle JSON")
    prepare_parser.add_argument("--rules", required=True, help="RuleSet rules JSON")
    prepare_parser.add_argument("--scope", required=True, help="ReviewScope JSON")
    prepare_parser.add_argument("--context", required=True, help="ReviewContext JSON")
    prepare_parser.add_argument(
        "--spec", required=True, help="ChangePreparationSpec JSON for the external executor"
    )
    prepare_parser.add_argument("--before-manifest", help="Baseline SourceManifest JSON")
    prepare_parser.set_defaults(handler=_prepare_change_command)
    verify_parser = subcommands.add_parser(
        "verify-change",
        help="Re-parse and verify a separately produced STEP artifact without executing CAD",
    )
    verify_parser.add_argument("--request", required=True, help="ChangeRequest JSON")
    verify_parser.add_argument("--plan", help="ChangePlan JSON")
    verify_parser.add_argument("--approval", help="ApprovalRecord JSON")
    verify_parser.add_argument("--execution", help="ExecutionRecord JSON")
    verify_parser.add_argument("--before-manifest", help="Baseline SourceManifest JSON")
    verify_parser.add_argument("--after-manifest", help="New SourceManifest JSON")
    verify_parser.add_argument("--origin-review", help="Original ReviewReport JSON")
    verify_parser.add_argument("--before", required=True, help="Baseline STEP file")
    verify_parser.add_argument("--after", required=True, help="New STEP file")
    verify_parser.add_argument(
        "--replay-relocated-output",
        action="store_true",
        help=(
            "Archived-evidence replay only: accept the same output filename outside its recorded "
            "absolute directory and disclose that relocation in the report"
        ),
    )
    verify_parser.set_defaults(handler=_verify_change_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    # JSON is UTF-8 by contract; do not inherit a legacy Windows console code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ValueError, KeyError, TypeError, ValidationError, json.JSONDecodeError) as error:
        print(json.dumps({"error": {"category": "configuration_or_input", "message": str(error)}}))
        return 2
    except Exception as error:
        print(json.dumps({"error": {"category": "internal", "message": str(error)}}))
        return 3


if __name__ == "__main__":
    sys.exit(main())
