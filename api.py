from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import time
from typing import List, Dict
from dotenv import load_dotenv

# --- Importy LangChain ---
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
    chat_history: List[Dict[str, str]] = [] 

# --- Funkcje pomocnicze ---
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
    print("Budowanie bazy...", flush=True)
    loader = PyPDFLoader(PDF_PATH)
    raw_pages = loader.load()
    full_text = ""
    for page in raw_pages: full_text += clean_text(page.page_content) + "\n\n"
    
    doc = Document(page_content=full_text, metadata={"source": PDF_PATH})
    splitter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=300, separators=["\nArt. ", "\n§ ", "\n\n", ". "], is_separator_regex=False)
    splits = splitter.split_documents([doc])
    
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
    
    for i, chunk in enumerate(splits):
        while True:
            try:
                vectorstore.add_documents([chunk])
                time.sleep(1.5)
                break
            except Exception as e:
                if "429" in str(e):
                    print("Limit Google (429). Czekam 60s...", flush=True)
                    time.sleep(60)
                else:
                    time.sleep(10)
    return True

# --- INTELIGENTNY ROUTER PYTAŃ ---
def get_standalone_question(chat_history, question):
    # ZMIANA: Printy są PRZED sprawdzeniem if not chat_history
    print(f"\n{'='*40}", flush=True)
    print(f"🔍 [DEBUG] Analiza pytania: '{question}'", flush=True)
    print(f"📜 [DEBUG] Rozmiar historii: {len(chat_history)}", flush=True)

    if not chat_history:
        print("❌ [DEBUG] Brak historii -> Zwracam pytanie bez zmian.", flush=True)
        print(f"{'='*40}\n", flush=True)
        return question

    print(f"✅ [DEBUG] Historia obecna. Uruchamiam LLM do kontekstu...", flush=True)
    
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-4:]])
    
    prompt = f"""Jesteś inteligentnym asystentem, który przygotowuje zapytania do bazy prawnej.
    
    Twoim zadaniem jest przeformułowanie pytania użytkownika tak, aby było ZROZUMIAŁE SAMODZIELNIE (bez historii).
    
    HISTORIA ROZMOWY:
    {history_text}
    
    NOWE PYTANIE UŻYTKOWNIKA: {question}
    
    INSTRUKCJE:
    1. Jeśli nowe pytanie to krótkie dopowiedzenie (np. "A poza biurem?", "A co z karami?", "A dla pracownika?"), połącz je z tematem z HISTORII.
       PRZYKŁAD: Historia="Czy mogę palić?", Pytanie="A poza biurem?" -> WYNIK="Czy pracownik może palić papierosy poza terenem biura?"
    2. Jeśli nowe pytanie zmienia temat (np. "Ile mam dni urlopu?"), pozostaw je BEZ ZMIAN.
    3. Nie odpowiadaj na pytanie. Zwróć tylko przeformułowane pytanie.
    
    WYNIKOWE PYTANIE DO BAZY:"""

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0.0)
    response = llm.invoke(prompt)
    
    standalone_q = response.content.strip()
    print(f"🤖 [DEBUG] Decyzja AI (Pytanie do bazy): '{standalone_q}'", flush=True)
    print(f"{'='*40}\n", flush=True)
    return standalone_q

# --- ENDPOINTY API ---

@app.get("/status")
def check_status():
    vs = get_vectorstore()
    return {"ready": vs is not None}

@app.post("/build")
def trigger_build():
    success = build_database()
    return {"success": success}

@app.post("/ask")
def ask_question(req: QueryRequest):
    """Główna funkcja czatu"""
    vectorstore = get_vectorstore()
    if not vectorstore:
        raise HTTPException(status_code=404, detail="Baza nie istnieje. Zbuduj ją najpierw.")

    # 1. Tłumaczenie pytania
    final_question = get_standalone_question(req.chat_history, req.question)

    # 2. Szukanie w bazie
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    context_docs = retriever.invoke(final_question)

    # 3. Generowanie odpowiedzi
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    
    system_prompt = (
        "Jesteś asystentem prawnym specjalizującym się w Kodeksie pracy. "
        "Udzielaj precyzyjnych odpowiedzi na pytanie użytkownika, bazując WYŁĄCZNIE na poniższym kontekście. "
        "Jeśli kontekst nie zawiera informacji na dany temat, powiedz wprost: 'Kodeks pracy nie reguluje tej kwestii bezpośrednio'. "
        "Zawsze podawaj numer Artykułu (Art.), jeśli jest w tekście.\n\n"
        "Kontekst:\n{context}"
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}")
    ])
    
    combine_docs_chain = create_stuff_documents_chain(llm, prompt)
    
    response = combine_docs_chain.invoke({
        "context": context_docs,
        "input": final_question 
    })
    
    sources = [doc.page_content.strip()[:300] + "..." for doc in context_docs]

    # --- NOWOŚĆ: LOGIKA FORMATOWANIA ODPOWIEDZI ---
    final_answer = response
    
    if req.question.strip().lower() != final_question.strip().lower():
        final_answer = f"Jeżeli pytasz: **{final_question}**, to odpowiedź brzmi:\n\n{response}"

    return {
        "answer": final_answer,
        "sources": sources
    }