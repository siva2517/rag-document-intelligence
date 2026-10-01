import uuid
from dataclasses import asdict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.ingest import Chunk


def _doc_filter(doc_id: str) -> Filter:
    return Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str, dim: int):
        self.client = client
        self.collection = collection
        if not client.collection_exists(collection):
            client.create_collection(collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        points = [
            PointStruct(id=str(uuid.uuid4()), vector=vec, payload=asdict(chunk))
            for chunk, vec in zip(chunks, vectors, strict=True)
        ]
        self.client.upsert(self.collection, points=points)

    def search(self, vector: list[float], top_k: int, doc_id: str | None = None) -> list[dict]:
        result = self.client.query_points(
            self.collection,
            query=vector,
            limit=top_k,
            query_filter=_doc_filter(doc_id) if doc_id else None,
        )
        return [{**p.payload, "score": p.score} for p in result.points]

    def chunks_for(self, doc_id: str) -> list[dict]:
        payloads, offset = [], None
        while True:
            points, offset = self.client.scroll(
                self.collection, scroll_filter=_doc_filter(doc_id), limit=256, offset=offset
            )
            payloads.extend(p.payload for p in points)
            if offset is None:
                return sorted(payloads, key=lambda p: p["index"])

    def list_documents(self) -> list[dict]:
        # The first chunk of each document doubles as its registry entry.
        first = Filter(must=[FieldCondition(key="index", match=MatchValue(value=0))])
        points, _ = self.client.scroll(self.collection, scroll_filter=first, limit=1000)
        return [{"doc_id": p.payload["doc_id"], "name": p.payload["doc_name"]} for p in points]

    def delete_document(self, doc_id: str) -> None:
        self.client.delete(self.collection, points_selector=_doc_filter(doc_id))
