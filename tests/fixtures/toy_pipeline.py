"""Toy RAG pipeline — S01 demo artifact.

Exercises both LLM and Retriever primitives so the runner produces
aggregated metrics with non-zero latency, tokens, and cost.
"""


def run(input_data, primitives):
    """Retrieve context, summarize with LLM, return structured answer."""
    query = input_data if isinstance(input_data, str) else "test query"

    # Retriever call — records metrics
    docs = primitives.retriever.retrieve(query)
    context = "\n".join(docs)

    # LLM call — records metrics
    answer = primitives.llm.complete(f"Summarize: {context}")

    return {"answer": answer, "sources": docs}
