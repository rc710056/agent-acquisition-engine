from typing import Dict, Set
from packages.shared_schemas.models import JobState

VALID_TRANSITIONS: Dict[JobState, Set[JobState]] = {
    JobState.CREATED: {JobState.UNDERSTANDING, JobState.INSPECTING, JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.UNDERSTANDING: {JobState.DISCOVERING, JobState.INSPECTING, JobState.NEEDS_CLARIFICATION, JobState.FAILED, JobState.CANCELLED},
    JobState.DISCOVERING: {JobState.INSPECTING, JobState.NEEDS_CLARIFICATION, JobState.FAILED, JobState.CANCELLED},
    JobState.INSPECTING: {JobState.AWAITING_APPROVAL, JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.NEEDS_CLARIFICATION: {JobState.UNDERSTANDING, JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.AWAITING_APPROVAL: {JobState.QUEUED, JobState.CANCELLED, JobState.FAILED, JobState.EXPIRED},
    JobState.QUEUED: {JobState.DOWNLOADING, JobState.CANCELLED, JobState.FAILED},
    JobState.DOWNLOADING: {JobState.VERIFYING, JobState.PARTIALLY_COMPLETED, JobState.FAILED, JobState.CANCELLED, JobState.QUEUED}, # QUEUED for retry
    JobState.VERIFYING: {JobState.COMPLETED, JobState.FAILED, JobState.PARTIALLY_COMPLETED},
    JobState.PARTIALLY_COMPLETED: {JobState.QUEUED, JobState.FAILED, JobState.COMPLETED},
    JobState.COMPLETED: set(),  # Terminal state
    JobState.FAILED: {JobState.QUEUED}, # Can be retried
    JobState.CANCELLED: set(), # Terminal state
    JobState.EXPIRED: set(),   # Terminal state
}

class InvalidStateTransitionError(Exception):
    pass

def validate_state_transition(current_state: str | JobState, new_state: str | JobState) -> bool:
    """
    Validates whether transition from current_state to new_state is permissible.
    Raises InvalidStateTransitionError if illegal.
    """
    curr = JobState(current_state)
    nxt = JobState(new_state)

    allowed = VALID_TRANSITIONS.get(curr, set())
    if nxt not in allowed:
        raise InvalidStateTransitionError(
            f"Illegal state transition from '{curr.value}' to '{nxt.value}'. Allowed targets: {[s.value for s in allowed]}"
        )
    return True
