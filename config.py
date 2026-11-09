# config.py
from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):

    # ─────────────────────────────────────────
    # LLM — Groq
    # ─────────────────────────────────────────
    groq_api_key: str

    # Primary model — use for reasoning, complex tasks
    groq_model_primary: str = "llama-3.1-70b-versatile"

    # Fast model — use for routing, classification
    # Cheaper and faster — saves tokens
    groq_model_fast: str = "allam-2-7b"
    embedding_model: Literal["local", "cohere"] = "cohere"
    cohere_api_key: str

    # ─────────────────────────────────────────
    # Vector Store
    # ─────────────────────────────────────────
    # Switch between "chroma" and "pinecone" via .env
    # No code changes needed anywhere else
    vector_store: Literal["chroma", "pinecone"] = "pinecone"

    # Chroma — local persistent storage
    chroma_persist_dir: str = "./data/chroma_db"

    # Pinecone — cloud
    pinecone_api_key: str = ""
    pinecone_index_name: str = "it-helpdesk-rag"

    otel_export: Literal["console", "file"] = "console"

    raw_csv_path: str = "./data/golden_it_support_tickets.csv"
    golden_subset_path: str = "./data/golden_subset.json"
    knowledge_base_path: str = "./data/knowledge_base.json"
    router_ground_truth_path: str = "./data/router_ground_truth.json"

    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Single instance — import this everywhere
# Never instantiate Settings() again anywhere else
settings = Settings()