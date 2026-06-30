"""Upstage API 래퍼.

문서 파싱(Document Parse), 임베딩(Embeddings), 판정(Solar Chat)을 한 곳에서 호출한다.
모든 엔드포인트는 https://api.upstage.ai/v1 기반.
429(요청 한도) 및 일시적 5xx 에러는 자동 재시도(지수 백오프)한다.
"""
import os
import time
import base64
import json
import requests

BASE = "https://api.upstage.ai/v1"
PAGE_LIMIT = 100  # Document Parse 동기 호출 1회 최대 페이지 수

MAX_RETRIES = 6
BACKOFF_BASE = 1.0  # 1차 대기 2초, 이후 4, 8, 16 ... 초


def _key() -> str:
    key = os.environ.get("UPSTAGE_API_KEY")
    if not key:
        raise RuntimeError("환경변수 UPSTAGE_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def _headers() -> dict:
    return {"Authorization": f"Bearer {_key()}"}


def _request(method: str, url: str, *, what: str, **kwargs) -> requests.Response:
    """429/5xx 발생 시 자동 재시도하는 요청 래퍼."""
    last = None
    for attempt in range(MAX_RETRIES):
        resp = requests.request(method, url, **kwargs)
        if resp.ok:
            return resp
        last = resp
        # 429(한도) 또는 5xx(일시적)면 대기 후 재시도
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else BACKOFF_BASE * (2 ** attempt)
            time.sleep(wait)
            continue
        # 그 외 에러는 즉시 중단
        break
    raise RuntimeError(f"{what} 실패 {last.status_code}: {last.text}")


def _parse_one(path: str, output_format: str) -> str:
    """단일 파일(100페이지 이하)을 파싱한다.

    ocr 모드: PDF면 'auto'(내장 텍스트 레이어 우선, 이미지만 OCR),
              이미지면 'force'(전체 OCR).
    """
    ocr_mode = "auto" if path.lower().endswith(".pdf") else "force"
    with open(path, "rb") as f:
        resp = _request(
            "POST", f"{BASE}/document-digitization",
            what="문서 파싱",
            headers=_headers(),
            files={"document": f},
            data={
                "model": "document-parse",
                "ocr": ocr_mode,
                "output_formats": f"['{output_format}']",
            },
            timeout=600,
        )
    content = resp.json().get("content", {})
    return content.get(output_format) or content.get("text") or ""


def parse_document(path: str, output_format: str = "markdown", max_pages: int | None = None) -> str:
    """약관 PDF를 구조화된 텍스트(기본 markdown)로 변환. 표 구조가 보존된다.

    PDF가 100페이지를 초과하면 자동으로 100페이지 단위로 나눠 파싱 후 합친다.
    max_pages 를 지정하면 앞에서 그 페이지까지만 처리한다(데모 속도용).
    """
    if not path.lower().endswith(".pdf"):
        return _parse_one(path, output_format)

    import tempfile
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(path)
    total = len(reader.pages)
    last = min(total, max_pages) if max_pages else total

    if last <= PAGE_LIMIT:
        if last == total:
            return _parse_one(path, output_format)
        # 앞 N페이지만 잘라서 처리
        writer = PdfWriter()
        for p in range(last):
            writer.add_page(reader.pages[p])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            writer.write(tmp)
            tmp_path = tmp.name
        try:
            return _parse_one(tmp_path, output_format)
        finally:
            os.unlink(tmp_path)

    parts = []
    for start in range(0, last, PAGE_LIMIT):
        end = min(start + PAGE_LIMIT, last)
        writer = PdfWriter()
        for p in range(start, end):
            writer.add_page(reader.pages[p])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            writer.write(tmp)
            tmp_path = tmp.name
        try:
            parts.append(_parse_one(tmp_path, output_format))
        finally:
            os.unlink(tmp_path)
    return "\n\n".join(parts)


def embed(texts, kind: str = "passage"):
    """텍스트 임베딩. kind='passage'(문서 색인용) / 'query'(질의용).

    엔드포인트: /v1/solar/embeddings
    모델: solar-embedding-1-large-passage / solar-embedding-1-large-query (4096차원)
    """
    if isinstance(texts, str):
        texts = [texts]
    resp = _request(
        "POST", f"{BASE}/solar/embeddings",
        what="임베딩 호출",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"model": f"solar-embedding-1-large-{kind}", "input": texts},
        timeout=60,
    )
    return [item["embedding"] for item in resp.json()["data"]]


def chat(messages, model: str = "solar-pro3", json_mode: bool = False, temperature: float = 0.1) -> str:
    """Solar Chat 호출. json_mode=True면 JSON object 형식으로 응답을 강제한다."""
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    resp = _request(
        "POST", f"{BASE}/chat/completions",
        what="Chat 호출",
        headers={**_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    return resp.json()["choices"][0]["message"]["content"]


# 보험증권/가입증서에서 뽑을 기본 스키마
CONTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "계약일": {"type": "string", "description": "보험 계약일 또는 가입일 (YYYY-MM-DD 형식으로)"},
        "상품명": {"type": "string", "description": "보험 상품 이름"},
        "피보험자": {"type": "string", "description": "피보험자 이름"},
        "보험기간": {"type": "string", "description": "보험 기간 또는 만기일"},
        "담보목록": {
            "type": "array",
            "description": "가입한 담보(보장)와 가입금액 목록",
            "items": {
                "type": "object",
                "properties": {
                    "담보명": {"type": "string"},
                    "가입금액": {"type": "string"},
                },
            },
        },
    },
}


def extract(path: str, schema: dict = CONTRACT_SCHEMA) -> dict:
    """보험증권/가입증서 등에서 스키마에 맞춘 구조화 정보를 추출한다 (Information Extract).

    엔드포인트 경로가 환경에 따라 다를 수 있어 두 가지를 순서대로 시도한다.
    """
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    mime = "application/pdf" if path.lower().endswith(".pdf") else "image/png"
    body = {
        "model": "information-extract",
        "messages": [{
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}],
        }],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "contract_schema", "schema": schema},
        },
    }
    headers = {**_headers(), "Content-Type": "application/json"}
    urls = [f"{BASE}/information-extraction/chat/completions", f"{BASE}/chat/completions"]
    last = None
    for url in urls:
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=300)
        except requests.RequestException as e:
            last = e
            continue
        if resp.ok:
            content = resp.json()["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"_raw": content}
        last = resp
        # 404/400처럼 경로 문제로 보이면 다음 URL 시도
        if resp.status_code in (404, 400, 405):
            continue
        break
    detail = last.text if hasattr(last, "text") else str(last)
    raise RuntimeError(f"정보 추출 실패: {detail}")


if __name__ == "__main__":
    # 0단계: 연결 확인용 간단 테스트
    print(chat([{"role": "user", "content": "한 문장으로 자기소개 해줘."}]))
