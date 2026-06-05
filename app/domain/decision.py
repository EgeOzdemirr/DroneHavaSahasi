from dataclasses import dataclass

from app.domain.enums import FriendStatus, ReasonCode


@dataclass(slots=True)
class DecisionResult:
    status: FriendStatus
    reason: ReasonCode
    confidence: int
    signature_valid: bool


def evaluate_decision(
    *,
    registered: bool,
    clock_ok: bool,
    replay_ok: bool,
    signature_ok: bool,
    mission_active: bool,
    policy_ok: bool = True,
) -> DecisionResult:
    if not registered:
        return DecisionResult(
            status=FriendStatus.unknown,
            reason=ReasonCode.not_in_registry,
            confidence=20,
            signature_valid=False,
        )

    if not clock_ok:
        return DecisionResult(
            status=FriendStatus.suspicious,
            reason=ReasonCode.clock_skew,
            confidence=10,
            signature_valid=False,
        )

    if not replay_ok:
        return DecisionResult(
            status=FriendStatus.suspicious,
            reason=ReasonCode.replay_detected,
            confidence=10,
            signature_valid=False,
        )

    if not signature_ok:
        return DecisionResult(
            status=FriendStatus.suspicious,
            reason=ReasonCode.bad_signature,
            confidence=10,
            signature_valid=False,
        )

    if not mission_active:
        return DecisionResult(
            status=FriendStatus.registered_not_authorized,
            reason=ReasonCode.no_active_mission,
            confidence=60,
            signature_valid=True,
        )

    if not policy_ok:
        return DecisionResult(
            status=FriendStatus.suspicious,
            reason=ReasonCode.policy_violation,
            confidence=40,
            signature_valid=True,
        )

    return DecisionResult(
        status=FriendStatus.authorized,
        reason=ReasonCode.ok,
        confidence=95,
        signature_valid=True,
    )

