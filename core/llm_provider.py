from langchain_groq import ChatGroq
from config import settings
import logging

logger = logging.getLogger(__name__)

def get_llm() -> ChatGroq:
    """
    get the primary llm provider
    """
    
    logger.debug(f"Primary model is being used : {settings.groq_model_primary}")
    return ChatGroq(
        model = settings.groq_model_primary,
        api_key= settings.groq_api_key,
        temperature=0.1,
        max_tokens=1024
    )
    
def get_llm_fast() -> ChatGroq:
    """
    Get the fastest LLM for small task
    """
    logger.debug(f"Primary model is being used : {settings.groq_model_fast}")
    return ChatGroq(
        model=settings.groq_model_fast,
        api_key=settings.groq_api_key,
        temperature=0.0,
        max_tokens=256
    )
    
    