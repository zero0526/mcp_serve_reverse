from typing import Any
from app.domain.lineage.entities import ReplaySpec
from app.domain.replay.entities import ReplayRequest
from app.domain.replay.policies import VariableResolver


class PrepareReplayUseCase:
    """Use case chuẩn bị ReplayRequest từ ReplaySpec bằng cách điền các biến động."""

    def execute(
        self,
        spec: ReplaySpec,
        variables: dict[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> ReplayRequest:
        vars_map = dict(variables or {})

        # 1. Tự động điền giá trị mặc định cho các biến chưa có
        for var_name in spec.required_variables:
            if var_name not in vars_map:
                vars_map[var_name] = VariableResolver.resolve_value(var_name, vars_map)

        # 2. Thay thế placeholder trong URL
        resolved_url = str(VariableResolver.substitute(spec.url_template, vars_map))

        # 3. Thay thế placeholder trong Headers
        resolved_headers: dict[str, str] = {}
        for h_key, h_val in spec.headers_template.items():
            resolved_headers[h_key] = str(VariableResolver.substitute(h_val, vars_map))

        # 4. Thay thế placeholder trong Body
        resolved_body = VariableResolver.substitute(spec.body_template, vars_map)

        return ReplayRequest(
            method=spec.method,
            url=resolved_url,
            headers=resolved_headers,
            body=resolved_body,
            timeout_seconds=timeout_seconds,
        )
