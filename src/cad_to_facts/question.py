"""Execute explicit question interpretations without turning them into source facts."""

from cad_to_facts.domain.question import (
    AnswerGap,
    AnswerReport,
    CountAnswer,
    InterpretationAnswer,
    QuestionInterpretation,
    QuestionSpec,
)
from cad_to_facts.domain.feature import FeatureQuery
from cad_to_facts.features import recognize_features
from cad_to_facts.domain.snapshot import ModelSnapshot
from cad_to_facts.identity import structured_hash
from cad_to_facts.orientation import infer_orientation
from cad_to_facts.resolution import resolve_target


def bind_question(spec: QuestionSpec) -> QuestionSpec:
    question_id = structured_hash("question", spec, exclude={"question_id"})
    return spec.model_copy(update={"question_id": question_id})


def _finish(question: QuestionSpec, answers: list[InterpretationAnswer], gaps: list[AnswerGap]):
    statuses = {answer.status for answer in answers}
    if "failed" in statuses:
        status = "failed"
    elif statuses == {"answered"} and answers:
        status = "answered"
    elif "partial" in statuses or "answered" in statuses:
        status = "partial"
    elif "ambiguous" in statuses:
        status = "ambiguous"
    elif "unresolved" in statuses:
        status = "unresolved"
    else:
        status = "unsupported"
    complete = status == "answered"
    report = AnswerReport(
        answer_id="0" * 64,
        status=status,
        complete=complete,
        question=question,
        answers=answers,
        gaps=gaps,
    )
    return report.model_copy(update={
        "answer_id": structured_hash("answer", report, exclude={"answer_id"})
    })


def _feature_answer(snapshot: ModelSnapshot, item: QuestionInterpretation):
    report = recognize_features(snapshot, FeatureQuery(
        kinds=item.feature_kinds,
        selector=item.selector,
    ))
    if report.status == "failed":
        return InterpretationAnswer(
            interpretation_id=item.interpretation_id,
            status="failed",
            features=report,
            feature_counts={
                kind: CountAnswer(
                    value=None,
                    state="unknown",
                    unit=(
                        "feature_candidates"
                        if item.evidence_policy == "candidates_allowed"
                        else "validated_features"
                    ),
                )
                for kind in item.feature_kinds
            } if item.intent == "feature_count" else {},
            gaps=[AnswerGap(
                code="FEATURE_EXECUTION_FAILED",
                message="The bounded feature recognizer could not read the assembly snapshot",
                interpretation_ids=[item.interpretation_id],
            )],
        )
    gaps = []
    counts = {}
    geometry = []
    if item.intent == "feature_geometry":
        geometry = [
            candidate.geometry for candidate in report.candidates
            if candidate.validation == "validated" and candidate.geometry is not None
        ]
        status = "partial"
        gaps.append(AnswerGap(
            code="GENERAL_FEATURE_GEOMETRY_INCOMPLETE",
            message=(
                "Only validated geometry from the bounded recognizer is returned; door/window and "
                "non-supported hole geometry remain unknown"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    else:
        for kind in item.feature_kinds:
            if item.evidence_policy == "candidates_allowed":
                value = report.candidate_counts[kind]
                state = "candidate"
            elif kind == "hole":
                value = report.validated_counts[kind]
                state = "observed"
            else:
                value = None
                state = "unknown"
            counts[kind] = CountAnswer(
                value=value,
                state=state,
                unit=(
                    "feature_candidates" if item.evidence_policy == "candidates_allowed"
                    else "validated_features"
                ),
                evidence_refs=[
                    candidate.feature_id for candidate in report.candidates
                    if candidate.kind == kind
                    and (
                        item.evidence_policy == "candidates_allowed"
                        or candidate.validation == "validated"
                    )
                ],
            )
        if item.evidence_policy == "candidates_allowed":
            status = "answered" if report.complete else "partial"
            if not report.complete:
                gaps.append(AnswerGap(
                    code="FEATURE_CANDIDATE_COUNT_OBSERVED_ONLY",
                    message="Feature candidate counts come from incomplete discovery or shape inspection",
                    interpretation_ids=[item.interpretation_id],
                ))
        else:
            status = "partial"
            gaps.append(AnswerGap(
                code="GENERAL_FEATURE_COUNT_UNKNOWN",
                message=(
                    "The values count only validated recognizer results, not all engineering features; "
                    "door/window validation and unsupported hole forms remain unknown"
                ),
                interpretation_ids=[item.interpretation_id],
            ))
    return InterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=status,
        features=report,
        feature_counts=counts,
        geometry=geometry,
        gaps=gaps,
    )


def _locate_answer(snapshot: ModelSnapshot, item: QuestionInterpretation):
    resolution = resolve_target(snapshot, item.selector)
    if resolution.status == "resolved":
        status = "answered" if resolution.complete else "partial"
    else:
        status = resolution.status
    gaps = []
    if resolution.status == "resolved" and not resolution.complete:
        gaps.append(AnswerGap(
            code="TARGET_RESOLUTION_INCOMPLETE",
            message="The unique target was found, but discovery or target geometry is incomplete",
            interpretation_ids=[item.interpretation_id],
        ))
    return InterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=status,
        resolution=resolution,
        gaps=gaps,
    )


def _orientation_answer(snapshot: ModelSnapshot, item: QuestionInterpretation):
    report = infer_orientation(snapshot, item.selector)
    status = report.status
    gaps = []
    if report.status == "resolved":
        status = (
            "answered"
            if item.evidence_policy == "candidates_allowed" and report.complete
            else "partial"
        )
        gaps.append(AnswerGap(
            code="DESIGN_FRONT_DECLARATION_UNAVAILABLE",
            message=(
                "The recommended direction is a bounding-box heuristic assumption, not a "
                "source-declared or functionally validated design front"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
        if not report.complete:
            gaps.append(AnswerGap(
                code="ORIENTATION_RESULT_INCOMPLETE",
                message="Target discovery or geometry is incomplete",
                interpretation_ids=[item.interpretation_id],
            ))
    return InterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=status,
        orientation=report,
        gaps=gaps,
    )


def _answer_one(snapshot: ModelSnapshot, item: QuestionInterpretation) -> InterpretationAnswer:
    if item.intent == "locate":
        return _locate_answer(snapshot, item)
    if item.intent == "orientation":
        return _orientation_answer(snapshot, item)
    if item.intent == "occurrence_count":
        resolution = resolve_target(snapshot, item.selector)
        gaps = []
        failed = resolution.status == "failed"
        if failed:
            gaps.append(AnswerGap(
                code="OCCURRENCE_COUNT_FAILED",
                message="The snapshot could not be read; occurrence quantity is unknown",
                interpretation_ids=[item.interpretation_id],
            ))
        elif not resolution.complete:
            gaps.append(AnswerGap(
                code="OCCURRENCE_COUNT_OBSERVED_ONLY",
                message="Occurrence discovery or candidate geometry is incomplete; the count is observed-only",
                interpretation_ids=[item.interpretation_id],
            ))
        return InterpretationAnswer(
            interpretation_id=item.interpretation_id,
            status=(
                "failed" if failed else "answered" if resolution.complete else "partial"
            ),
            resolution=resolution,
            occurrence_count=CountAnswer(
                value=None if failed else resolution.candidate_total,
                state=(
                    "unknown" if failed else "known" if resolution.complete else "observed"
                ),
                unit="occurrences",
                evidence_refs=(
                    [] if failed else [
                        candidate.occurrence_id for candidate in resolution.candidates
                    ]
                ),
            ),
            gaps=gaps,
        )
    if item.intent in {"feature_count", "feature_geometry"}:
        return _feature_answer(snapshot, item)
    return InterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status="unsupported",
        gaps=[AnswerGap(
            code="QUESTION_INTENT_UNSUPPORTED",
            message=f"The {item.intent} executor is not available in this slice",
            interpretation_ids=[item.interpretation_id],
        )],
    )


def answer_question(snapshot: ModelSnapshot, spec: QuestionSpec) -> AnswerReport:
    question = bind_question(spec)
    if not question.interpretations:
        messages = question.interpretation_gaps or ["No executable question interpretation was supplied"]
        return _finish(question, [], [AnswerGap(
            code="QUESTION_INTERPRETATION_UNSUPPORTED",
            message=message,
        ) for message in messages])
    answers = [_answer_one(snapshot, item) for item in question.interpretations]
    gaps = [gap for answer in answers for gap in answer.gaps]
    return _finish(question, answers, gaps)
