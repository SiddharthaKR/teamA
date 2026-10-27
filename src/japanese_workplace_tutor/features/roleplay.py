"""Situation roleplay feature: a challenge brief, then rubric feedback on the replies."""

from functools import partial

from ..core.items import LessonContent
from ..core.learner import ProfileRecord
from ..core.ports import DataClass
from ..llm.gateway import LLMGateway
from ..prompts import roleplay as prompts
from ..schemas.roleplay import (
    Comprehensibility,
    GeneratedChallenge,
    GraduationResult,
    Recovery,
    RoleplayJudgement,
    RoleplayVerdict,
    SituationChallenge,
)


def evaluate_graduation(verdict: RoleplayVerdict) -> GraduationResult:
    """Deterministic pass/fail from the model's per-criterion judgement.

    GRADUATE only when the goal was met, it was at least mostly comprehensible,
    the register was appropriate, and the curveball was at least partly handled.
    Comprehensibility is judged over grammatical perfection on purpose.
    """

    checks = {
        "goal": verdict.goal_achieved,
        "comprehensibility": verdict.comprehensible in (Comprehensibility.YES, Comprehensibility.MOSTLY),
        "register": verdict.register_appropriate,
        "recovery": verdict.recovered_from_curveball in (Recovery.YES, Recovery.PARTLY),
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    return GraduationResult(graduated=not failed, failed_criteria=failed)


class RoleplayCoach:
    def __init__(self, gateway: LLMGateway) -> None:
        self._run = partial(
            gateway.generate_validated,
            data_class=DataClass.PUBLIC,
            prompt_version=prompts.PROMPT_VERSION,
        )

    def generate_situation_challenge(
        self, content: LessonContent, profile: ProfileRecord
    ) -> GeneratedChallenge:
        """Build the brief + two-exchange roleplay challenge from a validated lesson."""

        package, provider_name = self._run(
            SituationChallenge,
            prompts.challenge_system_prompt(profile),
            prompts.challenge_user_prompt(content),
            "roleplay_brief",
            "We could not prepare a conversation challenge. Please retry.",
            lambda response: response,
        )
        return GeneratedChallenge(package, provider_name)

    def judge_roleplay(
        self,
        challenge: SituationChallenge,
        opening_reply: str,
        curveball_reply: str,
    ) -> RoleplayJudgement:
        """Score the learner's two Japanese replies against the challenge criteria."""

        package, provider_name = self._run(
            RoleplayVerdict,
            prompts.judge_system_prompt(),
            prompts.judge_user_prompt(challenge, opening_reply, curveball_reply),
            "roleplay_judge",
            "We could not evaluate the roleplay. Please retry.",
            lambda response: response,
        )
        return RoleplayJudgement(package, provider_name)
