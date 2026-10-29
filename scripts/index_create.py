from pinecone import Pinecone, ServerlessSpec
from config import settings

pc = Pinecone(api_key=settings.pinecone_api_key)

# pc.create_index(
#     name="it-helpdesk-rag",
#     spec=ServerlessSpec(
#         cloud="aws",
#         region="us-east-1",
#     ),
#     dimension=1024,
#     metric="cosine"
# )

description = pc.describe_index("it-helpdesk-rag")

print("Dimension:", description.dimension)
print("Host:", description.host)