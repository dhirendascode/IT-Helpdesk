from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_pinecone import PineconeVectorStore
from langchain_core.vectorstores import VectorStore
from config import settings
import logging
from langchain_cohere import CohereEmbeddings

logger = logging.getLogger(__name__)

def get_embedding() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model = "all-MiniLM-L6-v2"
    )
    
def get_embedding_cohere() -> CohereEmbeddings:
    return CohereEmbeddings(
        model = "embed-english-v3.0",
        cohere_api_key=settings.cohere_api_key
    )
    
def get_vector_store() -> VectorStore:
    """
Returns Chroma or Pinecone based on VECTOR_STORE env variable.
Everything else in the system calls this function only.
Switch provider by changing one line in .env
"""
    if (settings.embedding_model) == "cohere":
        embedding = get_embedding_cohere()
    else:
        embedding = get_embedding()
    # print(len(embedding.embed_query("test")))
    
    if (settings.vector_store) == "pinecone":
        logger.info("Vector store : Pinecone (cloud)")
        return PineconeVectorStore(
                index_name= settings.pinecone_index_name,
                embedding=embedding,
                pinecone_api_key=settings.pinecone_api_key
            )
       
        
    logger.info("Vector store : Pinecone (cloud)")
    print("*"*15)
    return Chroma(
                    collection_name = "IT_HELP_DESK",
                    embedding_function = embedding,
                    persist_directory=settings.chroma_persist_dir
                )
    
    
    