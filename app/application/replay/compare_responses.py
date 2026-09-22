from typing import Any
from app.domain.replay.entities import ReplayComparison, ReplayExecutionResult


class CompareResponsesUseCase:
    """Use case so sánh kết quả thực thi Replay với baseline capture ban đầu."""

    def execute(
        self,
        target_request_id: str,
        expected_status: int,
        expected_body: Any,
        expected_headers: dict[str, str] | None,
        actual_result: ReplayExecutionResult,
    ) -> ReplayComparison:
        status_match = expected_status == actual_result.status_code
        header_diffs: list[str] = []
        body_diffs: list[str] = []

        # 1. So sánh Content-Type trong headers nếu có
        if expected_headers:
            exp_ct = next((v for k, v in expected_headers.items() if k.lower() == "content-type"), None)
            act_ct = next((v for k, v in actual_result.headers.items() if k.lower() == "content-type"), None)
            if exp_ct and act_ct and exp_ct.split(";")[0] != act_ct.split(";")[0]:
                header_diffs.append(f"Content-Type mismatch: expected '{exp_ct}', got '{act_ct}'")

        # 2. So sánh Body
        body_match_ratio = 1.0
        if expected_body is not None and actual_result.body is not None:
            if isinstance(expected_body, dict) and isinstance(actual_result.body, dict):
                exp_keys = set(expected_body.keys())
                act_keys = set(actual_result.body.keys())

                missing_keys = exp_keys - act_keys
                extra_keys = act_keys - exp_keys

                for k in missing_keys:
                    body_diffs.append(f"Missing key in response body: '{k}'")
                for k in extra_keys:
                    body_diffs.append(f"Unexpected extra key in response body: '{k}'")

                common_keys = exp_keys & act_keys
                value_mismatches = 0
                for k in common_keys:
                    exp_val = expected_body[k]
                    act_val = actual_result.body[k]
                    # Nếu kiểu dữ liệu khác nhau
                    if type(exp_val) is not type(act_val):
                        body_diffs.append(
                            f"Key '{k}' type mismatch: expected {type(exp_val).__name__}, got {type(act_val).__name__}"
                        )
                        value_mismatches += 1

                total_comparisons = max(len(exp_keys | act_keys), 1)
                body_match_ratio = max(0.0, 1.0 - (len(body_diffs) / total_comparisons))
            elif expected_body != actual_result.body:
                body_diffs.append("Response body content differed from baseline")
                body_match_ratio = 0.5

        # 3. Tính tổng điểm tương đồng match_score (0.0 - 1.0)
        status_score = 0.5 if status_match else 0.0
        content_score = 0.5 * body_match_ratio
        match_score = round(status_score + content_score, 2)

        return ReplayComparison(
            target_request_id=target_request_id,
            status_match=status_match,
            expected_status=expected_status,
            actual_status=actual_result.status_code,
            header_diffs=header_diffs,
            body_diffs=body_diffs,
            match_score=match_score,
        )
