"""약관 청킹 + 벡터 색인/검색 (RAG).

ChromaDB(로컬, 인메모리)를 사용한다. 임베딩은 Upstage embedding API로 생성한다.
"""
import re
import chromadb

from . import upstage


def split_into_clauses(markdown: str, max_chars: int = 1200):
    """약관 markdown을 '제○조' 단위로 1차 분할하고, 너무 길면 재분할한다.

    반환: [{"조항": "제12조 ...", "text": "..."}, ...]
    """
    # "제 12 조", "제12조(보험금의 지급)" 등 패턴 기준 분할
    pattern = re.compile(r"(제\s*\d+\s*조[^\n]*)")
    parts = pattern.split(markdown)

    clauses = []
    # parts = [앞부분, 제목1, 본문1, 제목2, 본문2, ...]
    if parts and parts[0].strip():
        clauses.append({"조항": "서두", "text": parts[0].strip()})
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        full = f"{title}\n{body}".strip()
        # 길면 max_chars 단위로 재분할
        if len(full) <= max_chars:
            clauses.append({"조항": title, "text": full})
        else:
            for j in range(0, len(full), max_chars):
                clauses.append({"조항": title, "text": full[j:j + max_chars]})
    # 빈 항목 제거
    return [c for c in clauses if c["text"].strip()]


class ClauseIndex:
    """약관 조항 벡터 인덱스."""

    def __init__(self, name: str = "policy"):
        self.client = chromadb.Client()
        # 동일 이름이 있으면 재생성
        try:
            self.client.delete_collection(name)
        except Exception:
            pass
        self.col = self.client.create_collection(name)

    def build(self, clauses):
        """조항 리스트를 임베딩해 색인한다."""
        texts = [c["text"] for c in clauses]
        # 임베딩 API 호출 (배치가 크면 나눠서 호출 권장)
        embeddings = []
        for i in range(0, len(texts), 32):
            embeddings.extend(upstage.embed(texts[i:i + 32], kind="passage"))
        self.col.add(
            ids=[str(i) for i in range(len(clauses))],
            documents=texts,
            embeddings=embeddings,
            metadatas=[{"조항": c["조항"]} for c in clauses],
        )

    def search(self, query: str, k: int = 5):
        """질의와 유사한 조항 top-k 반환."""
        q_emb = upstage.embed(query, kind="query")[0]
        res = self.col.query(query_embeddings=[q_emb], n_results=k)
        out = []
        for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
            out.append({"조항": meta.get("조항", "?"), "text": doc})
        return out
