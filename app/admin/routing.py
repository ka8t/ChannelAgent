"""Model-routing service (#105): which model answers a turn when the agent itself
has none (Agent.model, #110, decision layer 1 — the caller decides that layer,
not this module). Layer 2 is a short ordered list of rules the admin configures
through the Admin API (app/api/routing_routes.py); layer 3 is the default model.
No classifier (D7, docs/COMPARISON_AJEAN.md): rules only, evaluated on what is
known about the message before any model call — no extra latency per turn.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.service import InvalidInputError, _clean_model, record_admin_event
from app.db.models import RoutingConfig, RoutingRule

# Singleton row: one routing table for the whole deployment, not per user or agent.
CONFIG_ID = 1
MATCH_TYPES = ("min_length", "command_prefix")
MAX_MATCH_VALUE_LENGTH = 200
MAX_RULES = 50


def _clean_match_value(match_type: str, value) -> str:
    if match_type == "min_length":
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidInputError("A min_length rule needs a positive integer match_value")
        return str(value)
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_MATCH_VALUE_LENGTH:
        raise InvalidInputError(
            f"A command_prefix rule needs a non-empty match_value up to "
            f"{MAX_MATCH_VALUE_LENGTH} characters"
        )
    return value


def _clean_rule(rule) -> dict:
    if not isinstance(rule, dict) or set(rule) - {"match_type", "match_value", "model"}:
        raise InvalidInputError("A rule has only match_type, match_value and model")
    match_type = rule.get("match_type")
    if match_type not in MATCH_TYPES:
        raise InvalidInputError(f"match_type is one of: {', '.join(MATCH_TYPES)}")
    model = _clean_model(rule.get("model"))
    if model is None:
        raise InvalidInputError("A rule needs a model")
    return {
        "match_type": match_type,
        "match_value": _clean_match_value(match_type, rule.get("match_value")),
        "model": model,
    }


def _clean_rules(rules) -> list[dict]:
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise InvalidInputError(f"At most {MAX_RULES} rules")
    return [_clean_rule(rule) for rule in rules]


def _clean_model_ctx_sizes(value) -> dict[str, int]:
    if not isinstance(value, dict):
        raise InvalidInputError("model_ctx_sizes is an object of model name to context size")
    cleaned: dict[str, int] = {}
    for name, size in value.items():
        model = _clean_model(name)
        if model is None or isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise InvalidInputError("model_ctx_sizes maps a valid model name to a positive integer")
        cleaned[model] = size
    return cleaned


async def get_routing(session: AsyncSession) -> dict:
    """The routing table as it stands: the default model, the rules in order, and
    the per-model context sizes. Empty defaults when nothing was ever set, so a
    turn behaves exactly as before #105 until an admin configures something.
    """
    config = await session.get(RoutingConfig, CONFIG_ID)
    rows = (
        (await session.execute(select(RoutingRule).order_by(RoutingRule.position))).scalars().all()
    )
    return {
        "default_model": config.default_model if config else None,
        "model_ctx_sizes": dict(config.model_ctx_sizes) if config else {},
        "rules": [
            {"match_type": r.match_type, "match_value": r.match_value, "model": r.model}
            for r in rows
        ],
    }


async def set_routing(
    session: AsyncSession,
    *,
    default_model=None,
    rules=None,
    model_ctx_sizes=None,
    actor: str,
) -> dict:
    """Replace the whole routing table: simpler and safer to reason about than a
    partial patch of an ordered list, and the admin UI always sends the full
    state anyway (mirrors PUT semantics).
    """
    cleaned_default = _clean_model(default_model)
    cleaned_rules = _clean_rules(rules if rules is not None else [])
    cleaned_ctx = _clean_model_ctx_sizes(model_ctx_sizes if model_ctx_sizes is not None else {})

    config = await session.get(RoutingConfig, CONFIG_ID)
    if config is None:
        config = RoutingConfig(id=CONFIG_ID)
        session.add(config)
    config.default_model = cleaned_default
    config.model_ctx_sizes = cleaned_ctx

    await session.execute(delete(RoutingRule))
    for position, rule in enumerate(cleaned_rules):
        session.add(RoutingRule(position=position, **rule))
    await session.flush()

    await record_admin_event(
        session,
        actor=actor,
        action="routing.set",
        target_type="routing",
        details={
            "default_model": cleaned_default,
            "rules": len(cleaned_rules),
            "model_ctx_sizes": cleaned_ctx,
        },
    )
    return await get_routing(session)


def select_model(*, text: str, rules: list[dict], default_model: str | None) -> str | None:
    """Decision layers 2 and 3 (layer 1, the agent's own model, is decided by the
    caller, app.graph.run_turn, before this is even called): the first rule that
    matches what is known about the message without a model call, or the default.
    """
    for rule in rules:
        if _rule_matches(rule, text):
            return rule["model"]
    return default_model


def _rule_matches(rule: dict, text: str) -> bool:
    if rule["match_type"] == "min_length":
        return len(text) >= int(rule["match_value"])
    if rule["match_type"] == "command_prefix":
        return text.startswith(rule["match_value"])
    return False
