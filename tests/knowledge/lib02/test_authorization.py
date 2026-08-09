import pytest

from knowledge.lib02.authorization import ActorContext, Role, Lab
from knowledge.lib02.failures import AuthorizationFailure


def test_lab_scoped_authorization():
    actor = ActorContext(actor_id="a1", role=Role.STRATEGY_LAB, lab=Lab.STRATEGY)
    # strategy cannot mutate global investment
    with pytest.raises(AuthorizationFailure):
        actor.authorize_mutation(Lab.GLOBAL_INVESTMENT)

    # strategy can mutate research
    actor.authorize_mutation(Lab.RESEARCH)


def test_system_architect_restrictions():
    sa = ActorContext(actor_id="sa", role=Role.SYSTEM_ARCHITECT, lab=Lab.GLOBAL_INVESTMENT)
    with pytest.raises(AuthorizationFailure):
        sa.authorize_mutation(Lab.RESEARCH)

    # system architect can mutate global investment internals
    sa.authorize_mutation(Lab.GLOBAL_INVESTMENT)


def test_governance_monitor_read_only():
    gm = ActorContext(actor_id="gm", role=Role.GOVERNANCE_MONITOR, lab=Lab.GLOBAL_INVESTMENT)
    with pytest.raises(AuthorizationFailure):
        gm.authorize_mutation(Lab.GLOBAL_INVESTMENT)
