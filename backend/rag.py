"""약관 청킹 + 벡터 색인/검색 (RAG).

ChromaDB(로컬, 인메모리)를 사용한다. 임베딩은 Upstage embedding API로 생성한다.
임베딩 모델 토큰 한도(4000)를 넘지 않도록 모든 청크 크기와 배치 크기를 제한한다.
"""
import re
import chromadb

from . import upstage

MAX_CHUNK_CHARS = 1000   # 개별 청크 최대 글자수
CHUNK_OVERLAP = 200      # 청크 간 겹침 (조항이 토막날 때 문맥 보존)
BATCH_CHAR_LIMIT = 2000  # 임베딩 1회 요청 글자수 합계 상한
DEFAULT_K = 10           # 검색 시 가져올 조항 수


def _hard_split(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = CHUNK_OVERLAP):
    """어떤 텍스트든 max_chars 이하 조각들로 쪼갠다. overlap 만큼 겹쳐서 문맥을 보존한다."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    step = max(1, max_chars - overlap)
    return [text[j:j + max_chars] for j in range(0, len(text), step)]


def split_into_clauses(markdown: str, max_chars: int = MAX_CHUNK_CHARS):
    """약관 markdown을 '제○조' 단위로 나누되, 모든 조각을 max_chars 이하로 강제한다.

    '제○조' 패턴이 안 잡히는 약관도 안전하게 처리된다.
    반환: [{"조항": "제12조 ...", "text": "..."}, ...]
    """
    # "제 12 조", "제12조(...)", "제 12 관" 등 폭넓게 매칭
    pattern = re.compile(r"(제\s*\d+\s*(?:조|관)[^\n]*)")
    parts = pattern.split(markdown)

    raw = []
    if parts and parts[0].strip():
        raw.append(("서두", parts[0]))
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        raw.append((title, f"{title}\n{body}"))

    clauses = []
    for title, text in raw:
        for piece in _hard_split(text, max_chars):
            clauses.append({"조항": title, "text": piece})
    return clauses


def _embed_in_batches(texts, kind):
    """글자수 합계 기준으로 배치를 묶어 임베딩한다 (토큰 한도 초과 방지)."""
    embeddings = []
    batch, batch_chars = [], 0
    for t in texts:
        for piece in _hard_split(t, MAX_CHUNK_CHARS, overlap=0):
            if batch and batch_chars + len(piece) > BATCH_CHAR_LIMIT:
                embeddings.extend(upstage.embed(batch, kind=kind))
                batch, batch_chars = [], 0
            batch.append(piece)
            batch_chars += len(piece)
    if batch:
        embeddings.extend(upstage.embed(batch, kind=kind))
    return embeddings


class ClauseIndex:
    """약관 조항 벡터 인덱스."""

    def __init__(self, name: str = "policy"):
        self.client = chromadb.Client()
        try:
            self.client.delete_collection(name)
        except Exception:
            pass
        self.col = self.client.create_collection(name)

    def build(self, clauses):
        texts = [c["text"] for c in clauses]
        embeddings = _embed_in_batches(texts, kind="passage")
        self.col.add(
            ids=[str(i) for i in range(len(clauses))],
            documents=texts,
            embeddings=embeddings,
            metadatas=[{"조항": c["조항"]} for c in clauses],
        )

    def search(self, query: str, k: int = DEFAULT_K):
        q_emb = upstage.embed(query, kind="query")[0]
        res = self.col.query(query_embeddings=[q_emb], n_results=k)
        out = []
        for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
            out.append({"조항": meta.get("조항", "?"), "text": doc})
        return out
