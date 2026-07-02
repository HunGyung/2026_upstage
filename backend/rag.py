"""약관 청킹 + 벡터 색인/검색 (RAG).

개선점:
- 조항/별표 단위로 나누고, 모든 조각 앞에 상위 제목을 붙여 문맥을 보존한다.
- 질문을 약관 용어로 확장(query expansion)한 뒤 검색한다.
- 검색 후보를 Solar로 재정렬(rerank)해 노이즈를 줄인다.
"""
import re
import json
import chromadb

from . import upstage

MAX_CHUNK_CHARS = 1000   # 개별 청크 최대 글자수
CHUNK_OVERLAP = 200      # 청크 간 겹침
BATCH_CHAR_LIMIT = 2000  # 임베딩 1회 요청 글자수 합계 상한
K_RETRIEVE = 20          # 1차 벡터 검색 후보 수
K_FINAL = 8              # 재정렬 후 최종 사용 조항 수


def _hard_split(text, max_chars=MAX_CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    step = max(1, max_chars - overlap)
    return [text[j:j + max_chars] for j in range(0, len(text), step)]


def split_into_clauses(markdown, max_chars=MAX_CHUNK_CHARS):
    """약관을 '제○조/제○관/별표' 단위로 나누고, 각 조각에 상위 제목을 붙인다."""
    # 조항(제○조/제○관)과 별표 제목을 경계로 분할
    pattern = re.compile(r"(제\s*\d+\s*(?:조|관)[^\n]*|\[?\s*별\s*표[^\n]*)")
    parts = pattern.split(markdown)

    raw = []
    if parts and parts[0].strip():
        raw.append(("서두", parts[0]))
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        raw.append((title, body))

    clauses = []
    for title, body in raw:
        pieces = _hard_split(body.strip(), max_chars) or [""]
        for piece in pieces:
            text = f"[{title}]\n{piece}".strip()
            clauses.append({"조항": title, "text": text})
    return clauses


def _embed_in_batches(texts, kind):
    embeddings = []
    batch, batch_chars = [], 0
    for t in texts:
        if batch and batch_chars + len(t) > BATCH_CHAR_LIMIT:
            embeddings.extend(upstage.embed(batch, kind=kind))
            batch, batch_chars = [], 0
        batch.append(t)
        batch_chars += len(t)
    if batch:
        embeddings.extend(upstage.embed(batch, kind=kind))
    return embeddings


def expand_query(question):
    """사용자 질문을 약관에서 쓰일 법한 용어·동의어로 확장한 검색어를 만든다."""
    msg = [
        {"role": "system", "content":
            "너는 보험 약관 검색 도우미다. 사용자의 일상어 질문을, 약관 본문에 나올 법한 "
            "용어·동의어·의학용어로 확장한 '검색어 한 줄'로 바꿔라. 질병이면 정식 병명과 "
            "질병분류코드 가능성도 덧붙여라. 설명 없이 검색어만 출력."},
        {"role": "user", "content": question},
    ]
    try:
        return upstage.chat(msg, temperature=0.0)
    except Exception:
        return question


def _rerank(question, candidates, top_n):
    """후보 조항을 Solar로 재정렬해 관련 높은 것만 고른다."""
    if not candidates:
        return []
    listing = "\n".join(f"{i}: {c['text'][:300]}" for i, c in enumerate(candidates))
    msg = [
        {"role": "system", "content":
            "질문에 답하는 데 가장 관련 있는 조항 번호만 관련도 높은 순으로 JSON 배열로 반환하라. "
            "예: [3, 0, 7]. 다른 설명은 하지 마라."},
        {"role": "user", "content": f"질문: {question}\n\n조항들:\n{listing}\n\n최대 {top_n}개 번호를 JSON 배열로."},
    ]
    try:
        raw = upstage.chat(msg, temperature=0.0)
        nums = json.loads(re.search(r"\[.*\]", raw, re.S).group())
        picked = [candidates[i] for i in nums if isinstance(i, int) and 0 <= i < len(candidates)]
        return picked[:top_n] or candidates[:top_n]
    except Exception:
        return candidates[:top_n]


class ClauseIndex:
    """약관 조항 벡터 인덱스."""

    def __init__(self, name="policy"):
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

    def search(self, query, k=K_FINAL):
        """순수 벡터 검색."""
        q_emb = upstage.embed(query, kind="query")[0]
        res = self.col.query(query_embeddings=[q_emb], n_results=k)
        out = []
        for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
            out.append({"조항": meta.get("조항", "?"), "text": doc})
        return out

    def smart_search(self, question, k_final=K_FINAL, k_retrieve=K_RETRIEVE, rerank=True):
        """질문 확장 -> 벡터 검색 -> 재정렬."""
        query = f"{question} {expand_query(question)}"
        candidates = self.search(query, k=k_retrieve)
        if rerank:
            return _rerank(question, candidates, k_final)
        return candidates[:k_final]
