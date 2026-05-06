from app.domains.content_ingestion.providers.embedding_providers import FakeEmbeddingProvider


def test_fake_embedding_provider_deterministic_and_dim():
    prov = FakeEmbeddingProvider()
    texts = ["hello", "world"]

    v1 = __import__("asyncio").run(prov.embed(texts))
    v2 = __import__("asyncio").run(prov.embed(texts))

    assert v1 == v2
    assert len(v1) == 2
    assert len(v1[0]) == prov.get_embedding_dimension()

