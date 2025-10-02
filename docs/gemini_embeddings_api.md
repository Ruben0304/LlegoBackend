
# Gemini API — Embeddings

The **Gemini API** provides *text embedding* models to generate vector representations of words, phrases, sentences, and code.  
These embeddings power advanced NLP tasks such as:

- **Semantic search**
- **Classification**
- **Clustering**

They provide more accurate, context-aware results than keyword-based approaches.

---

## RAG Use Case
A common use case is building **Retrieval Augmented Generation (RAG)** systems, where embeddings:

- Improve factual accuracy.  
- Retrieve relevant information from knowledge bases.  
- Enrich the input prompt for language models.  

---

## Generating Embeddings

Example in **Python**:

```python
from google import genai

client = genai.Client()

result = client.models.embed_content(
    model="gemini-embedding-001",
    contents="What is the meaning of life?"
)

print(result.embeddings)
```

Generating embeddings for multiple chunks:

```python
from google import genai

client = genai.Client()

result = client.models.embed_content(
    model="gemini-embedding-001",
    contents=[
        "What is the meaning of life?",
        "What is the purpose of existence?",
        "How do I bake a cake?"
    ]
)

for embedding in result.embeddings:
    print(embedding)
```

---

## Specifying Task Type

To optimize embeddings, specify `task_type`.  
Example: **SEMANTIC_SIMILARITY**

```python
from google import genai
from google.genai import types
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

client = genai.Client()

texts = [
    "What is the meaning of life?",
    "What is the purpose of existence?",
    "How do I bake a cake?"
]

result = [
    np.array(e.values) for e in client.models.embed_content(
        model="gemini-embedding-001",
        contents=texts,
        config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY")
    ).embeddings
]

embeddings_matrix = np.array(result)
similarity_matrix = cosine_similarity(embeddings_matrix)

for i, text1 in enumerate(texts):
    for j in range(i + 1, len(texts)):
        text2 = texts[j]
        print(f"Similarity between '{text1}' and '{text2}': {similarity_matrix[i, j]:.4f}")
```

Example output:

```
Similarity between 'What is the meaning of life?' and 'What is the purpose of existence?': 0.9481
Similarity between 'What is the meaning of life?' and 'How do I bake a cake?': 0.7471
Similarity between 'What is the purpose of existence?' and 'How do I bake a cake?': 0.7371
```

---

## Supported Task Types

| Task type              | Description                                                       | Examples                               |
|------------------------|-------------------------------------------------------------------|----------------------------------------|
| SEMANTIC_SIMILARITY    | Optimized to assess text similarity.                              | Recommendation systems, deduplication  |
| CLASSIFICATION         | Optimized for classification tasks.                               | Sentiment analysis, spam detection     |
| CLUSTERING             | Optimized to cluster texts based on similarities.                 | Document organization, market research |
| RETRIEVAL_DOCUMENT     | Optimized for document search.                                    | Articles, books, web pages             |
| RETRIEVAL_QUERY        | Optimized for general queries.                                    | Custom search engines                  |
| CODE_RETRIEVAL_QUERY   | Optimized for retrieving code blocks from natural language.       | Code suggestions and search            |
| QUESTION_ANSWERING     | Optimized for QA systems.                                         | Chatbots                               |
| FACT_VERIFICATION      | Optimized for fact-checking systems.                              | Automated verification                 |

---

## Controlling Embedding Size

The model `gemini-embedding-001` uses **Matryoshka Representation Learning (MRL)**.  
You can set the output size with `output_dimensionality`.

Example:

```python
from google import genai
from google.genai import types

client = genai.Client()

result = client.models.embed_content(
    model="gemini-embedding-001",
    contents="What is the meaning of life?",
    config=types.EmbedContentConfig(output_dimensionality=768)
)

[embedding_obj] = result.embeddings
print(len(embedding_obj.values))  # -> 768
```

### Normalizing for Smaller Dimensions
```python
import numpy as np

embedding_values_np = np.array(embedding_obj.values)
normed_embedding = embedding_values_np / np.linalg.norm(embedding_values_np)

print(len(normed_embedding))
print(np.linalg.norm(normed_embedding))  # ≈ 1.0
```

### Benchmarks (MTEB scores)

| Dimension | MTEB Score |
|-----------|------------|
| 2048      | 68.16      |
| 1536      | 68.17      |
| 768       | 67.99      |
| 512       | 67.55      |
| 256       | 66.19      |
| 128       | 63.31      |

---

## Use Cases

- **RAG**: enrich prompts with retrieved context.  
- **Information retrieval**: semantic document search.  
- **Search reranking**: reorder by semantic relevance.  
- **Anomaly detection**: find outliers in embeddings.  
- **Classification**: sentiment, spam, topic labeling.  
- **Clustering**: group and visualize semantic relations.  

---

## Storing Embeddings

Recommended to use vector databases for indexing and retrieval:  

- **Google Cloud**: BigQuery, AlloyDB, Cloud SQL.  
- **3rd Party**: ChromaDB, QDrant, Weaviate, Pinecone.  

---

## Model Versions

- **Stable**: `gemini-embedding-001`  
- **Experimental (deprecated Oct 2025)**: `gemini-embedding-exp-03-07`  

**Limits:**
- Input tokens: 2,048  
- Output dimension: 128 – 3072 (recommended: 768, 1536, 3072)  

Last update: **June 2025**  

---

## Batch Embeddings

If latency is not critical, use **Batch API** for higher throughput at half the cost.

---

## Responsible Use Notice

The Gemini Embedding model **does not generate new content**, it transforms input into vectors.  
Users are responsible for the data they provide and their downstream applications.  

See:  
- [Google Terms of Service](https://policies.google.com/terms)  
- [Prohibited Use Policy](https://ai.google.dev/policies/use_policy)

---

## Deprecation

The following models will be deprecated in **October 2025**:

- `embedding-001`  
- `embedding-gecko-001`  
- `gemini-embedding-exp-03-07`  

---
