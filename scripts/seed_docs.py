import json
import os
import sys
from langchain_core.documents import Document
from vector_store.vector_store import get_embedding, get_vector_store
from config import settings

def seed():
    kb_path="data/golden_it_support_tickets.json"
    
    with open(kb_path, "r") as file:
        records = json.load(file)
    
    docs = []    
    for r in records:
        docs.append(Document(
            page_content=(
                f"Issue : {r['initial_message']}\n"
                f"Resolution: {r['resolution_summary']}"
            ),
            metadata={
                "ticket_id":          r["ticket_id"],
                "scenario_key":       r["scenario_key"],
                "issue_type":         r["issue_type"],
                "product_area":       r["product_area"],
                "priority":           r["priority"],
                "resolution_summary": r["resolution_summary"]
            }
        ))
        
    vector_store = get_vector_store()
    vector_store.add_documents(docs)
    print(f"Seeded {len(docs)} documents")
    print(f"Provider : {settings.vector_store}")
    print(f"Sample doc: {docs[0].page_content[:100]}...")
    
if __name__ == '__main__':
    seed()