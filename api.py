from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import time
from dotenv import load_dotenv

# --- Twoje importy RAG ---
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

# --- KONFIGURACJA ---
load_dotenv()
PDF_PATH = "Kodeks_pracy.pdf"
DB_PATH = "./chroma_db_kp"
EMBEDDING_MODEL = "models/gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash"

app = FastAPI()

# Zezwalamy Reactowi na łączenie się z Pythonem (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modele danych ---
class QueryRequest(BaseModel):
    question: str

# --- Funkcje pomocnicze (Twoje sprawdzone metody) ---
def clean_text(text):
    lines = text.split('\n')
    cleaned = [l for l in lines if "Kancelaria Sejmu" not in l and not re.search(r'\d{4}-\d{2}-\d{2}', l) and not l.strip().isdigit()]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(cleaned))

def get_vectorstore():
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    if os.path.exists(DB_PATH) and os.listdir(DB_PATH):
        return Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
    return None

def build_database():
    if not os.path.exists(PDF_PATH): return False
    print("Budowanie bazy...")
    loader = PyPDFLoader(PDF_PATH)
    raw_pages = loader.load()
    full_text = ""
    for page in raw_pages: full_text += clean_text(page.page_content) + "\n\n"
    
    doc = Document(page_content=full_text, metadata={"source": PDF_PATH})
    splitter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=300, separators=["\nArt. ", "\n§ ", "\n\n", ". "], is_separator_regex=False)
    splits = splitter.split_documents([doc])
    
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
    
    # Pancerna pętla
    for i, chunk in enumerate(splits):
        while True:
            try:
                vectorstore.add_documents([chunk])
                time.sleep(1.5)
                break
            except Exception as e:
                if "429" in str(e):
                    print("Limit Google (429). Czekam 60s...")
                    time.sleep(60)
                else:
                    time.sleep(10)
    return True

# --- ENDPOINTY API ---

@app.get("/status")
def check_status():
    """Sprawdza czy baza jest gotowa"""
    vs = get_vectorstore()
    return {"ready": vs is not None}

@app.post("/build")
def trigger_build():
    """Wymusza budowę bazy"""
    success = build_database()
    return {"success": success}

@app.post("/ask")
def ask_question(req: QueryRequest):
    """Główna funkcja czatu"""
    vectorstore = get_vectorstore()
    if not vectorstore:
        raise HTTPException(status_code=404, detail="Baza nie istnieje. Zbuduj ją najpierw.")

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    
    system_prompt = (
        "Jesteś ekspertem prawa pracy. Odpowiadaj na podstawie kontekstu. "
        "Zawsze podawaj podstawę prawną (Art.).\n\n{context}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", "{input}")])
    chain = create_retrieval_chain(retriever, create_stuff_documents_chain(llm, prompt))
    
    response = chain.invoke({"input": req.question})
    
    # Formatujemy źródła
    sources = [doc.page_content[:200] + "..." for doc in response["context"]]
    
    return {
        "answer": response["answer"],
        "sources": sources
    }