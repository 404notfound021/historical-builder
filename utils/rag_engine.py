"""本地 RAG 检索引擎 —— 分块 → 嵌入 → 向量检索"""

from pathlib import Path
import chromadb
from chromadb.config import Settings


class RAGEngine:
    def __init__(self, config: dict, embedding_client):
        self.chunk_size = config["processing"].get("chunk_size", 2000)
        self.chunk_overlap = config["processing"].get("chunk_overlap", 200)
        self.embedding_client = embedding_client

        self.chroma_client = chromadb.Client(Settings(anonymized_telemetry=False))

    def load_book(self, source_path: Path) -> str:
        """加载原始典籍文本"""
        with open(source_path, encoding="utf-8") as f:
            return f.read()

    def chunk_text(self, text: str) -> list[str]:
        """按块大小切分文本，保留重叠上下文"""
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.chunk_overlap
        return chunks

    def build_index(self, book_name: str, chunks: list[str]):
        """构建向量索引"""
        collection = self.chroma_client.get_or_create_collection(name=book_name)
        embeddings = self.embedding_client.embed(chunks)
        collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=[f"{book_name}_{i}" for i in range(len(chunks))],
        )
        return collection

    def search(self, book_name: str, query: str, top_k: int = 5) -> list[str]:
        """检索相关文本块"""
        collection = self.chroma_client.get_collection(name=book_name)
        query_embedding = self.embedding_client.embed([query])
        results = collection.query(query_embeddings=query_embedding, n_results=top_k)
        return results["documents"][0] if results["documents"] else []
