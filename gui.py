import streamlit as st
import os
import re
import time
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document


st.set_page_config(
    page_title="Asystent Prawa Pracy",
    page_icon="⚖️",
    layout="wide"
)


load_dotenv()
if not os.getenv("GOOGLE_API_KEY"):
    st.error("Brak klucza API w pliku .env")
    st.stop()

PDF_PATH = "Kodeks_pracy.pdf"
DB_PATH = "./chroma_db_kp"
EMBEDDING_MODEL = "models/gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash"


def clean_text(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if "Kancelaria Sejmu" in line: continue
        if re.search(r'\d{4}-\d{2}-\d{2}', line): continue
        if line.strip().isdigit(): continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    return re.sub(r'\n{3,}', '\n\n', text)

def build_database_gui():
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    if not os.path.exists(PDF_PATH):
        st.error(f"Brak pliku {PDF_PATH}")
        return None

    status_text.text(" Ładowanie pliku PDF...")
    loader = PyPDFLoader(PDF_PATH)
    raw_pages = loader.load()
    
    full_text = ""
    for page in raw_pages:
        full_text += clean_text(page.page_content) + "\n\n"
    
    cleaned_doc = Document(page_content=full_text, metadata={"source": PDF_PATH})

    status_text.text(" Dzielenie na artykuły...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=3000,
        chunk_overlap=300,
        separators=["\nArt. ", "\n§ ", "\n\n", ". ", " ", ""],
        is_separator_regex=False
    )
    splits = text_splitter.split_documents([cleaned_doc])
    
    status_text.text(f" Rozpoczynam generowanie wektorów (Total: {len(splits)} fragmentów)...")
    
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
    
    total = len(splits)
    
    # Pancerna pętla w wersji GUI
    for i, doc in enumerate(splits):
        while True:
            try:
                # Aktualizacja paska postępu
                progress = (i + 1) / total
                progress_bar.progress(progress)
                status_text.text(f"Wysyłanie fragmentu {i+1}/{total}...")
                
                vectorstore.add_documents([doc])
                time.sleep(1.5) # Krótka przerwa
                break 
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "ResourceExhausted" in error_msg:
                    status_text.warning(f" Limit Google (429). Czekam 60s na reset...")
                    time.sleep(60)
                    status_text.text(f" Wznawiam...")
                else:
                    status_text.error(f"Inny błąd: {e}. Czekam 10s...")
                    time.sleep(10)
    
    status_text.success(" Baza danych gotowa!")
    time.sleep(1)
    status_text.empty()
    progress_bar.empty()
    return vectorstore

@st.cache_resource
def get_rag_chain():
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    
    # Sprawdzenie czy baza istnieje
    if os.path.exists(DB_PATH) and os.listdir(DB_PATH):
        # Szybkie sprawdzenie czy nie pusta
        try:
            vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
            if vectorstore._collection.count() == 0:
                vectorstore = None
        except:
            vectorstore = None
    else:
        vectorstore = None

    # Jeśli brak bazy, musimy ją zbudować (ale nie wewnątrz cache!)
    if vectorstore is None:
        return None 

    # LLM
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 5})

    system_prompt = (
        "Jesteś ekspertem prawa pracy. "
        "Użyj poniższego kontekstu, aby odpowiedzieć na pytanie. "
        "Odpowiedź musi zawierać podstawę prawną (Art.).\n\n"
        "{context}"
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])
    
    chain = create_retrieval_chain(retriever, create_stuff_documents_chain(llm, prompt))
    return chain

# --- UI LOGIKA ---
st.title("⚖️ Asystent Kodeksu Pracy")
st.markdown(f"Model: **{LLM_MODEL}** | Baza: **{EMBEDDING_MODEL}**")

# Sprawdzenie czy baza istnieje, jeśli nie -> przycisk budowania
if not os.path.exists(DB_PATH) or not os.listdir(DB_PATH):
    st.warning(" Nie wykryto bazy danych.")
    if st.button(" Zbuduj bazę wiedzy (ok. 15 min)"):
        with st.spinner("Praca w toku..."):
            build_database_gui()
            st.rerun() # Odśwież stronę po zakończeniu
    st.stop() # Zatrzymaj renderowanie reszty strony

# Pobranie łańcucha RAG
rag_chain = get_rag_chain()

if rag_chain is None:
    st.error("Błąd ładowania bazy. Spróbuj usunąć folder chroma_db_kp i odświeżyć stronę.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Wyświetlanie historii
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Obsługa wejścia użytkownika
if prompt := st.chat_input("Zadaj pytanie (np. Czy urlop przechodzi na kolejny rok?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analizuję przepisy..."):
            response = rag_chain.invoke({"input": prompt})
            answer = response["answer"]
            st.markdown(answer)
            
            # Pokaż źródła w rozwijanym panelu
            with st.expander("🔍 Zobacz podstawę prawną (fragmenty źródłowe)"):
                for i, doc in enumerate(response["context"]):
                    st.caption(f"Fragment {i+1} (Źródło: {doc.metadata.get('source', 'PDF')})")
                    st.text(doc.page_content)

    st.session_state.messages.append({"role": "assistant", "content": answer})
