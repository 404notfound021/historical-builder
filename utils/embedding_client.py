"""嵌入向量客户端 —— BGE-M3 本地嵌入 或 云端 API"""


class EmbeddingClient:
    def __init__(self, config: dict):
        self.provider = config["embedding"].get("provider", "local")
        self.model_name = config["embedding"].get("model", "BAAI/bge-m3")
        self._model = None

    def _load_model(self):
        if self._model is None and self.provider == "local":
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "local":
            self._load_model()
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        else:
            raise NotImplementedError(f"Provider {self.provider} not supported yet")
