import json
from typing import Any
from app.domain.lineage.entities import ReplaySpec
from app.domain.replay.entities import SynthesizedCode
from app.ports.replay import CodeSynthesizerPort


class CodeSynthesizer(CodeSynthesizerPort):
    """Adapter tổng hợp mã nguồn tự động từ ReplaySpec."""

    def synthesize(
        self,
        spec: ReplaySpec,
        language: str = "python",
    ) -> SynthesizedCode:
        lang = language.lower().strip()
        if lang in ["python", "py"]:
            return self._synthesize_python(spec)
        elif lang in ["curl", "bash", "sh"]:
            return self._synthesize_curl(spec)
        elif lang in ["typescript", "ts", "javascript", "js"]:
            return self._synthesize_typescript(spec)
        else:
            raise ValueError(f"Unsupported code synthesis language: '{language}'")

    def _build_param_docs(self, spec: ReplaySpec) -> list[str]:
        """Tạo chú thích nguồn gốc Lineage cho từng tham số."""
        docs = []
        for var in spec.required_variables:
            lineage = spec.parameter_lineages.get(var) or spec.parameter_lineages.get("request")
            if lineage:
                source_desc = f"{lineage.origin_type}"
                if lineage.origin_key:
                    source_desc += f" ('{lineage.origin_key}')"
                docs.append(f"        {var}: Origin {source_desc}, confidence {lineage.overall_confidence}")
            else:
                docs.append(f"        {var}: User supplied dynamic parameter")
        return docs

    def _synthesize_python(self, spec: ReplaySpec) -> SynthesizedCode:
        var_args = []
        for v in spec.required_variables:
            var_args.append(f"{v}: Any")

        if not var_args:
            args_str = "client: httpx.AsyncClient | None = None"
        else:
            args_str = ", ".join(var_args) + ", client: httpx.AsyncClient | None = None"

        doc_lines = self._build_param_docs(spec)
        docstring = "\n".join(doc_lines)

        headers_json = json.dumps(spec.headers_template, indent=8)
        body_json = json.dumps(spec.body_template, indent=8) if spec.body_template is not None else "None"

        # Thay thế placeholder kiểu {{var}} bằng f-string hoặc nội suy
        # Để code Python sinh ra sạch và đúng cú pháp
        headers_code = self._template_to_python_dict(spec.headers_template)
        body_code = self._template_to_python_dict(spec.body_template)

        code = f'''import httpx
from typing import Any

async def execute_request({args_str}) -> httpx.Response:
    """
    Tái hiện tự động request {spec.method} {spec.url_template}
    Được sinh tự động từ task_id: {spec.task_id}

    Parameters:
{docstring}
    """
    url = "{spec.url_template}"
    headers = {headers_code}
    payload = {body_code}

    should_close = False
    if client is None:
        client = httpx.AsyncClient()
        should_close = True

    try:
        response = await client.request(
            method="{spec.method}",
            url=url,
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        return response
    finally:
        if should_close:
            await client.aclose()
'''
        return SynthesizedCode(
            task_id=spec.task_id,
            target_request_id=spec.target_request_id,
            language="python",
            code=code.strip(),
            variables=spec.required_variables,
            description=f"Python httpx script for {spec.method} {spec.url_template}",
        )

    def _template_to_python_dict(self, data: Any) -> str:
        """Chuyển dict template {{var}} thành code Python dictionary sử dụng biến runtime."""
        if data is None:
            return "None"
        if isinstance(data, dict):
            entries = []
            for k, v in data.items():
                val_repr = self._template_value_to_python(v)
                entries.append(f'        "{k}": {val_repr}')
            return "{\n" + ",\n".join(entries) + "\n    }"
        return repr(data)

    def _template_value_to_python(self, val: Any) -> str:
        if isinstance(val, str):
            if val.startswith("{{") and val.endswith("}}"):
                var_name = val[2:-2].strip()
                return var_name
            if "{{" in val and "}}" in val:
                # Dạng "Bearer {{auth_token}}" -> f"Bearer {auth_token}"
                formatted = val.replace("{{", "{").replace("}}", "}")
                return f'f"{formatted}"'
            return repr(val)
        return repr(val)

    def _synthesize_curl(self, spec: ReplaySpec) -> SynthesizedCode:
        lines = [f"curl -X {spec.method} '{spec.url_template}' \\"]
        for k, v in spec.headers_template.items():
            lines.append(f"  -H '{k}: {v}' \\")
        if spec.body_template is not None:
            body_str = json.dumps(spec.body_template, ensure_ascii=False)
            lines.append(f"  -d '{body_str}' \\")
        # Bỏ dấu gạch nối cuối cùng
        curl_cmd = "\n".join(lines).rstrip(" \\")

        return SynthesizedCode(
            task_id=spec.task_id,
            target_request_id=spec.target_request_id,
            language="curl",
            code=curl_cmd,
            variables=spec.required_variables,
            description=f"cURL command for {spec.method} {spec.url_template}",
        )

    def _synthesize_typescript(self, spec: ReplaySpec) -> SynthesizedCode:
        type_fields = [f"  {v}: any;" for v in spec.required_variables]
        type_def = "\n".join(type_fields) if type_fields else "  // No variables required"

        headers_code = json.dumps(spec.headers_template, indent=4)
        body_code = json.dumps(spec.body_template, indent=4) if spec.body_template else "undefined"

        code = f'''export interface ExecuteRequestParams {{
{type_def}
}}

export async function executeRequest(params: ExecuteRequestParams): Promise<Response> {{
    const url = "{spec.url_template}";
    const headers = {headers_code};
    const body = {body_code};

    return await fetch(url, {{
        method: "{spec.method}",
        headers: headers as Record<string, string>,
        body: body ? JSON.stringify(body) : undefined,
    }});
}}
'''
        return SynthesizedCode(
            task_id=spec.task_id,
            target_request_id=spec.target_request_id,
            language="typescript",
            code=code.strip(),
            variables=spec.required_variables,
            description=f"TypeScript fetch function for {spec.method} {spec.url_template}",
        )
