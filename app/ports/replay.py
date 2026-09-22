from typing import Protocol
from app.domain.lineage.entities import ReplaySpec
from app.domain.replay.entities import ReplayExecutionResult, ReplayRequest, SynthesizedCode
from app.domain.replay.policies import ReplaySafetyPolicy


class HTTPReplayExecutorPort(Protocol):
    """Port giao tiếp thực thi HTTP request độc lập."""

    async def execute(
        self,
        request: ReplayRequest,
        policy: ReplaySafetyPolicy | None = None,
    ) -> ReplayExecutionResult:
        """Thực thi request và trả về kết quả."""
        ...


class CodeSynthesizerPort(Protocol):
    """Port giao tiếp tổng hợp mã nguồn tự động."""

    def synthesize(
        self,
        spec: ReplaySpec,
        language: str = "python",
    ) -> SynthesizedCode:
        """Sinh mã nguồn từ ReplaySpec theo ngôn ngữ chỉ định."""
        ...
