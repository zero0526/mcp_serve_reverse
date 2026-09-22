from app.adapters.synthesis.code_synthesizer import CodeSynthesizer
from app.application.lineage.generate_replay_spec import GenerateReplaySpecUseCase
from app.domain.lineage.entities import ReplaySpec
from app.domain.replay.entities import SynthesizedCode
from app.ports.replay import CodeSynthesizerPort


class SynthesizeCodeUseCase:
    """Use case sinh mã nguồn độc lập từ task_id & target_request_id hoặc ReplaySpec."""

    def __init__(
        self,
        generate_spec_use_case: GenerateReplaySpecUseCase | None = None,
        synthesizer: CodeSynthesizerPort | None = None,
    ):
        self.generate_spec_use_case = generate_spec_use_case
        self.synthesizer = synthesizer or CodeSynthesizer()

    async def execute(
        self,
        task_id: str,
        target_request_id: str,
        language: str = "python",
        spec: ReplaySpec | None = None,
    ) -> SynthesizedCode:
        replay_spec = spec
        if replay_spec is None:
            if not self.generate_spec_use_case:
                raise ValueError(
                    "generate_spec_use_case is required when spec is not directly provided"
                )
            replay_spec = await self.generate_spec_use_case.execute(
                task_id=task_id,
                target_request_id=target_request_id,
            )

        return self.synthesizer.synthesize(replay_spec, language=language)
