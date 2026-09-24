from types import SimpleNamespace
from uuid import uuid4

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableSequence

from app.pipelines.langchain_rag import (
    ApplicationChatModel,
    ApplicationEmbeddings,
    compile_answer_chain,
)
from app.providers import generation
from app.providers.embeddings import EmbeddingConfig
from app.schemas.index import RetrievalRequest


class Vectors:
    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[1.0, 0.0, 0.0] for _ in texts]


class Chat:
    def __init__(self):
        self.calls = []

    def generate(self, messages, config):
        self.calls.append((messages, config))
        return generation.Completion(
            "Grounded [S1]", "test/chat", {"total_tokens": 7}, 0.0001
        )


def test_application_embedding_provider_uses_langchain_contract(monkeypatch):
    provider = Vectors()
    config = EmbeddingConfig(
        provider="openrouter",
        model="test/embed",
        dimensions=3,
        endpoint_id="endpoint",
        revision="1",
    )
    monkeypatch.setattr(
        "app.pipelines.langchain_rag.embeddings.provider_for", lambda saved: provider
    )
    adapter = ApplicationEmbeddings(config, 3)

    assert isinstance(adapter, Embeddings)
    assert adapter.embed_query("question") == [1.0, 0.0, 0.0]
    assert adapter.embed_documents(["one", "two"]) == [
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
    ]
    assert provider.calls == [["question"], ["one", "two"]]


def test_application_chat_provider_uses_langchain_contract():
    provider = Chat()
    config = {
        "provider": "openrouter",
        "model": "test/chat",
        "max_tokens": 128,
        "temperature": 0,
    }
    adapter = ApplicationChatModel(provider=provider, generation_config=config)

    assert isinstance(adapter, BaseChatModel)
    message = adapter.invoke([("system", "policy"), ("human", "question")])
    assert message.content == "Grounded [S1]"
    assert message.response_metadata["usage"] == {"total_tokens": 7}
    assert message.response_metadata["cost_usd"] == 0.0001
    assert provider.calls == [
        (
            [
                {"role": "system", "content": "policy"},
                {"role": "user", "content": "question"},
            ],
            config,
        )
    ]


def test_compiler_builds_lcel_runnable_sequence(monkeypatch):
    embedding_config = EmbeddingConfig(
        provider="openrouter",
        model="test/embed",
        dimensions=3,
        endpoint_id="endpoint",
        revision="1",
    )
    monkeypatch.setattr(
        "app.pipelines.langchain_rag.generation.provider_for", lambda: Chat()
    )
    chain, trace = compile_answer_chain(
        session=object(),
        project_id=uuid4(),
        index=SimpleNamespace(
            id=uuid4(),
            version=1,
            dimensions=3,
            embedding_config=embedding_config.model_dump(),
        ),
        request=RetrievalRequest(index_id=uuid4(), query="question", top_k=2),
        generation_config={
            "provider": "openrouter",
            "model": "test/chat",
            "context_tokens": 2048,
            "max_tokens": 128,
            "temperature": 0,
        },
        prompt_template=None,
        node_ids={
            "question": "question-ui",
            "retriever": "retriever-ui",
            "prompt": "prompt-ui",
            "llm": "llm-ui",
            "answer": "answer-ui",
        },
    )

    assert isinstance(chain, RunnableSequence)
    assert trace.updates == {}
