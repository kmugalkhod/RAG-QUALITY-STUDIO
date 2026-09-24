"""Compile the supported answer graph into a LangChain LCEL runnable.

The application owns graph validation, persistence, provider policy and SQL. LangChain
provides the runtime contracts and composition layer; it never receives arbitrary code
or an unvalidated graph from the browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import version
from time import monotonic
from typing import Any, Callable

from langchain_core.documents import Document as LangChainDocument
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import (
    RunnableLambda,
    RunnablePassthrough,
    RunnableSequence,
)
from pydantic import ConfigDict, Field

from app.pipelines.generation import build_context, validate_citations
from app.providers import embeddings, generation
from app.schemas.index import RetrievalRequest
from app.services import indexes

NODE_ORDER = ("question", "retriever", "prompt", "llm", "answer")


def runtime_snapshot(node_ids: dict[str, str] | None = None) -> dict[str, Any]:
    """Return the execution-engine identity persisted with every accepted run."""

    return {
        "framework": "langchain",
        "langchain_version": version("langchain"),
        "langchain_core_version": version("langchain-core"),
        "composition": "LCEL RunnableSequence",
        "node_order": [(node_ids or {}).get(kind, kind) for kind in NODE_ORDER],
    }


class ApplicationEmbeddings(Embeddings):
    """LangChain embedding interface over the bounded application provider."""

    def __init__(self, config: embeddings.EmbeddingConfig, dimensions: int):
        self.config = config
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embeddings.validate_vectors(
            embeddings.provider_for(self.config).embed(texts),
            len(texts),
            self.dimensions,
        )

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _provider_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    roles = {
        SystemMessage: "system",
        HumanMessage: "user",
        AIMessage: "assistant",
    }
    result = []
    for message in messages:
        role = next(
            (value for kind, value in roles.items() if isinstance(message, kind)), None
        )
        if role is None or not isinstance(message.content, str):
            raise generation.GenerationError(
                "The answer pipeline produced an unsupported chat message."
            )
        result.append({"role": role, "content": message.content})
    return result


class ApplicationChatModel(BaseChatModel):
    """LangChain chat-model interface over the no-retry OpenRouter adapter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: Any = Field(exclude=True)
    generation_config: dict[str, Any]

    @property
    def _llm_type(self) -> str:
        return "rag-quality-studio-openrouter"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "provider": self.generation_config["provider"],
            "model": self.generation_config["model"],
            "max_tokens": self.generation_config["max_tokens"],
            "temperature": self.generation_config["temperature"],
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        if stop:
            raise generation.GenerationError(
                "Stop sequences are not supported by this answer pipeline."
            )
        completion = self.provider.generate(
            _provider_messages(messages), self.generation_config
        )
        metadata = {
            "model": completion.model,
            "usage": completion.usage,
            "cost_usd": completion.cost_usd,
            "finish_reason": completion.finish_reason,
        }
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=completion.answer,
                        response_metadata=metadata,
                    )
                )
            ],
            llm_output={"model_name": completion.model},
        )


class ProjectIndexRetriever(BaseRetriever):
    """LangChain retriever backed by the existing project-scoped pgvector query."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session: Any = Field(exclude=True)
    project_id: Any
    request: RetrievalRequest
    query_embeddings: Any = Field(exclude=True)
    last_result: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def _get_relevant_documents(
        self, query: str, *, run_manager
    ) -> list[LangChainDocument]:
        request = self.request.model_copy(update={"query": query})
        self.last_result = indexes.retrieve(
            self.session,
            self.project_id,
            request,
            query_embeddings=self.query_embeddings,
        )
        return [
            LangChainDocument(page_content=item["text"], metadata={"evidence": item})
            for item in self.last_result["items"]
        ]


@dataclass
class ChainTrace:
    updates: dict[str, Any] = field(default_factory=dict)


def _elapsed(started: float) -> float:
    return round((monotonic() - started) * 1000, 3)


def compile_answer_chain(
    *,
    session,
    project_id,
    index,
    request: RetrievalRequest,
    generation_config: dict[str, Any],
    prompt_template: str | None,
    node_ids: dict[str, str] | None = None,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
    before_provider: Callable[[], None] | None = None,
) -> tuple[RunnableSequence, ChainTrace]:
    """Compile one validated five-node answer graph into an LCEL sequence."""

    ids = node_ids or {kind: kind for kind in NODE_ORDER}
    trace = ChainTrace()
    embedding_config = embeddings.EmbeddingConfig.model_validate(index.embedding_config)
    langchain_embeddings = ApplicationEmbeddings(embedding_config, index.dimensions)
    retriever = ProjectIndexRetriever(
        session=session,
        project_id=project_id,
        request=request,
        query_embeddings=langchain_embeddings,
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", "{system}"), ("human", "{payload}")]
    ).with_config(run_name=ids["prompt"])
    chat_model = ApplicationChatModel(
        provider=generation.provider_for(), generation_config=generation_config
    )

    def question_stage(data: dict[str, Any]) -> dict[str, Any]:
        return {"question": data["question"]}

    def retrieval_stage(state: dict[str, Any]) -> dict[str, Any]:
        started = monotonic()
        try:
            if before_provider:
                before_provider()
            documents = retriever.invoke(
                state["question"], config={"run_name": ids["retriever"]}
            )
            result = retriever.last_result
            updates = {
                "retrieval_ms": _elapsed(started),
                "retrieval_result": result,
            }
            trace.updates.update(updates)
            return {**state, "documents": documents, **updates}
        except Exception:
            trace.updates["retrieval_ms"] = _elapsed(started)
            raise

    def context_stage(state: dict[str, Any]) -> dict[str, Any]:
        items = [document.metadata["evidence"] for document in state["documents"]]
        sources, messages = build_context(
            state["question"], items, generation_config, prompt_template
        )
        updates = {
            "evidence": sources,
            "messages": messages,
            "retrieved_count": len(items),
            "omitted_count": len(items) - len(sources),
        }
        trace.updates.update(updates)
        return {
            **state,
            **updates,
            "prompt_input": {
                "system": messages[0]["content"],
                "payload": messages[1]["content"],
            },
        }

    def checkpoint_stage(state: dict[str, Any]) -> dict[str, Any]:
        if checkpoint:
            checkpoint(trace.updates)
        return state

    def generation_stage(state: dict[str, Any]) -> dict[str, Any]:
        if not state["evidence"]:
            updates = {
                "generation_ms": 0,
                "answer": "INSUFFICIENT_EVIDENCE: No evidence was retrieved from this index.",
                "actual_model": None,
                "finish_reason": "stop",
                "usage": None,
                "cost_usd": None,
                "cost_basis": None,
            }
            trace.updates.update(updates)
            return {**state, **updates}
        started = monotonic()
        try:
            if before_provider:
                before_provider()
            message = chat_model.invoke(
                state["prompt_value"], config={"run_name": ids["llm"]}
            )
        finally:
            trace.updates["generation_ms"] = _elapsed(started)
        metadata = message.response_metadata
        updates = {
            "generation_ms": trace.updates["generation_ms"],
            "answer": message.content,
            "actual_model": metadata.get("model"),
            "finish_reason": metadata.get("finish_reason", "stop"),
            "usage": metadata.get("usage"),
            "cost_usd": metadata.get("cost_usd"),
            "cost_basis": (
                "OpenRouter reported generation cost (USD); excludes retrieval embeddings"
                if metadata.get("cost_usd") is not None
                else None
            ),
        }
        trace.updates.update(updates)
        return {**state, **updates}

    def answer_stage(state: dict[str, Any]) -> dict[str, Any]:
        answer = state["answer"]
        updates = {"citations": validate_citations(answer, state["evidence"])}
        trace.updates.update(updates)
        return {**state, **updates}

    question = RunnableLambda(question_stage, name=ids["question"])
    retrieval = RunnableLambda(retrieval_stage, name=ids["retriever"])
    context = RunnableLambda(context_stage, name="select_grounded_context")
    prompt_assignment = RunnablePassthrough.assign(
        prompt_value=(
            RunnableLambda(lambda state: state["prompt_input"], name="prompt_input")
            | prompt
        )
    )
    persist_evidence = RunnableLambda(checkpoint_stage, name="checkpoint_evidence")
    llm = RunnableLambda(generation_stage, name=ids["llm"])
    answer = RunnableLambda(answer_stage, name=ids["answer"])
    chain = (
        question
        | retrieval
        | context
        | prompt_assignment
        | persist_evidence
        | llm
        | answer
    )
    return chain, trace
