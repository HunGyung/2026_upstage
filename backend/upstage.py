"""Upstage API 래퍼.

문서 파싱(Document Parse), 임베딩(Embeddings), 판정(Solar Chat)을 한 곳에서 호출한다.
모든 엔드포인트는 https://api.upstage.ai/v1 (OpenAI 호환) 기반.
"""
import os
import requests

BASE = "https://api.upstage.ai/v1"


def _key() -> str:
    key = os.environ.get("UPSTAGE_API_KEY")
    if not key:
        raise RuntimeError("환경변수 UPSTAGE_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def _headers() -> dict:
    return {"Authorization": f"Bearer {_key()}"}


def parse_document(path: str, output_format: str = "markdown") -> str:
    """약관 PDF를 구조화된 텍스트(기본 markdown)로 변환. 표 구조가 보존된다."""
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE}/document-digitization",
            headers=_headers(),
            files={"document": f},
            data={"model": "document-parse", "output_formats": f"['{output_format}']"},
            timeout=300,
        )
    resp.raise_for_status()
    data = resp.json()
    # 응답 구조: { "content": { "markdown": "...", "html": "...", "text": "..." }, ... }
    content = data.get("content", {})
    return content.get(output_format) or content.get("text") or ""


def embed(texts, kind: str = "passage"):
    """텍스트 임베딩. kind='passage'(문서 색인용) / 'query'(질의용)."""
    if isinstance(texts, str):
        texts = [texts]
    resp = requests.post(
        f"{BASE}/embeddings",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"model": f"embedding-{kind}", "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]


def chat(messages, model: str = "solar-pro2", json_mode: bool = False, temperature: float = 0.1) -> str:
    """Solar Chat 호출. json_mode=True면 JSON object 형식으로 응답을 강제한다."""
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    resp = requests.post(
        f"{BASE}/chat/completions",
        headers={**_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    # 0단계: 연결 확인용 간단 테스트
    print(chat([{"role": "user", "content": "한 문장으로 자기소개 해줘."}]))
