"""A deliberately bounded, offline grammar for common model questions.

This parser produces reviewable interpretations. It does not establish functional
semantics, and unsupported wording is returned as an explicit interpretation gap.
"""

import re

from cad_to_facts.domain.question import QuestionInterpretation, QuestionSpec
from cad_to_facts.domain.view import CameraSpecification, SpatialConstraint, TargetSelector


_FEATURE_ALIASES = {
    "door": ("door", "门"),
    "window": ("window", "窗"),
    "hole": ("hole", "孔"),
}
_SPATIAL_PHRASES = (
    ("left_of", ("左侧", "左边", "左方"), r"\bleft(?:\s+of|\s+side)?\b"),
    ("right_of", ("右侧", "右边", "右方"), r"\bright(?:\s+of|\s+side)?\b"),
    ("above", ("上方", "上面", "上部"), r"\b(?:above|on\s+top\s+of)\b"),
    ("below", ("下方", "下面", "下部"), r"\b(?:below|beneath|underneath)\b"),
    ("in_front_of", ("前方", "前面"), r"\bin\s+front\s+of\b"),
    ("behind", ("后方", "后面", "背部"), r"\bbehind\b"),
)


def _mentioned_kinds(text: str) -> list[str]:
    kinds = []
    for kind, (english, chinese) in _FEATURE_ALIASES.items():
        if chinese in text or re.search(rf"(?<![a-z]){english}s?(?![a-z])", text):
            kinds.append(kind)
    return kinds


def _spatial_relation(text: str) -> str | None:
    for relation, chinese_phrases, english_pattern in _SPATIAL_PHRASES:
        if any(phrase in text for phrase in chinese_phrases) or re.search(
            english_pattern, text
        ):
            return relation
    return None


def _has_any(text: str, phrases: tuple[str, ...], pattern: str) -> bool:
    return any(phrase in text for phrase in phrases) or re.search(pattern, text) is not None


def _unsupported(text: str, message: str) -> QuestionSpec:
    return QuestionSpec(
        original_text=text,
        interpretation_basis="deterministic_grammar",
        interpretation_gaps=[message],
    )


def parse_question(original_text: str) -> QuestionSpec:
    """Translate only explicitly supported Chinese/English forms into a QuestionSpec."""
    text = original_text.strip()
    if not text:
        raise ValueError("Question text must not be empty")
    normalized = re.sub(r"\s+", " ", text.casefold())
    kinds = _mentioned_kinds(normalized)
    if not kinds:
        return _unsupported(
            text,
            "The bounded offline grammar currently recognizes only door/window/hole questions; "
            "use an explicit QuestionSpec for other subjects",
        )

    wants_orientation = _has_any(normalized, ("正面",), r"\bfront\s+(?:face|side|direction)\b")
    wants_locate = _has_any(normalized, ("哪里", "在哪"), r"\bwhere\b")
    wants_count = _has_any(
        normalized, ("多少", "几个", "数量"), r"\b(?:how\s+many|count|number\s+of)\b"
    )
    wants_geometry = _has_any(
        normalized,
        ("尺寸", "大小", "形状", "几何"),
        r"\b(?:size|sizes|shape|shapes|geometry|radius|diameter|dimensions?)\b",
    )
    relation = _spatial_relation(normalized)
    wants_locate = wants_locate or relation is not None

    if any(phrase in normalized for phrase in ("附近", "旁边", "邻近")) or re.search(
        r"\bnear(?:by)?\b", normalized
    ):
        return _unsupported(
            text,
            "Natural-language near requires an explicit distance in a user/agent QuestionSpec; "
            "the offline grammar does not invent max_distance_mm",
        )

    aliases = [
        alias for kind in kinds for alias in _FEATURE_ALIASES[kind]
    ]
    selector = TargetSelector(name_contains_any=aliases)
    assumptions = []
    notes = [
        "Declared occurrence/definition name aliases select candidates; they do not prove "
        "door, window, or hole function"
    ]
    if relation is not None:
        selector = selector.model_copy(update={"spatial": [SpatialConstraint(
            relation=relation,
            reference=TargetSelector(is_root=True),
            frame=CameraSpecification(preset="front"),
        )]})
        assumptions.append(
            "The implicit spatial reference is the union of all root-occurrence bounding boxes "
            "in the global front camera; left/right/up/down are not source-declared semantics"
        )

    interpretations = []
    if wants_orientation:
        interpretations.append(QuestionInterpretation(
            interpretation_id="orientation",
            intent="orientation",
            selector=selector,
            notes=[*notes, "Design front is inferred only by the bounded orientation heuristic"],
        ))
    elif wants_locate:
        interpretations.append(QuestionInterpretation(
            interpretation_id="locate",
            intent="locate",
            selector=selector,
            notes=notes,
        ))
    else:
        if wants_count:
            interpretations.append(QuestionInterpretation(
                interpretation_id="feature-count",
                intent="feature_count",
                feature_kinds=kinds,
                notes=notes,
            ))
        if wants_geometry:
            interpretations.append(QuestionInterpretation(
                interpretation_id="feature-geometry",
                intent="feature_geometry",
                feature_kinds=kinds,
                notes=notes,
            ))

    if not interpretations:
        return _unsupported(
            text,
            "The bounded offline grammar supports locating door/window/hole candidates, counting "
            "recognized features, requesting validated feature geometry, and assumed-front "
            "orientation; this wording has no supported intent",
        )
    return QuestionSpec(
        original_text=text,
        interpretation_basis="deterministic_grammar",
        interpretations=interpretations,
        assumptions=assumptions,
    )
