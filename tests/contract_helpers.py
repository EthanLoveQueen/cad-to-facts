from cad_to_facts.contract import (
    bind_context,
    bind_factset,
    bind_requirement_bundle,
    bind_ruleset,
    bind_scope,
    bind_snapshot,
)
from cad_to_facts.domain.review import ReviewRequest


def bind_request(request: ReviewRequest) -> ReviewRequest:
    """Bind a fixture exactly as the CLI binds JSON review inputs."""

    snapshot = bind_snapshot(request.snapshot)
    factset = request.factset.model_copy(
        update={
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_content_hash": snapshot.snapshot_content_hash,
        }
    )
    bundle = bind_requirement_bundle(request.ruleset.requirement_bundle)
    ruleset = bind_ruleset(
        request.ruleset.model_copy(update={"requirement_bundle": bundle})
    )
    return request.model_copy(
        update={
            "snapshot": snapshot,
            "factset": bind_factset(factset),
            "ruleset": ruleset,
            "scope": bind_scope(request.scope),
            "context": bind_context(request.context),
        }
    )
