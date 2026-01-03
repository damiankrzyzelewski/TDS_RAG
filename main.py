import os
import re
import sys
import time  # <--- NOWOŚĆ: Biblioteka do robienia przerw
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

# ==========================================
# KONFIGURACJA
# ==========================================
load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    print("❌ BŁĄD: Nie znaleziono klucza GOOGLE_API_KEY w pliku .env")
    sys.exit(1)

PDF_PATH = "Kodeks_pracy.pdf"
DB_PATH = "./chroma_db_kp"
EMBEDDING_MODEL = "models/gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash" 

# ==========================================
# 1. FUNKCJA CZYSZCZĄCA
# ==========================================
def clean_text(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if "Kancelaria Sejmu" in line: continue
        if re.search(r'\d{4}-\d{2}-\d{2}', line): continue
        if line.strip().isdigit(): continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

# ==========================================
# 2. TWORZENIE BAZY DANYCH (Z NAPRAWIONYM BATCHINGIEM)
# ==========================================
def prepare_database():
    print(f"--- 1. Przetwarzanie pliku: {PDF_PATH} ---")
    
    if not os.path.exists(PDF_PATH):
        print(f"❌ BŁĄD: Nie widzę pliku {PDF_PATH} w folderze!")
        return None

    # Ładowanie
    loader = PyPDFLoader(PDF_PATH)
    raw_pages = loader.load()
    print(f"   Załadowano {len(raw_pages)} stron.")

    # Czyszczenie
    full_text = ""
    for page in raw_pages:
        full_text += clean_text(page.page_content) + "\n\n"
    
    cleaned_doc = Document(page_content=full_text, metadata={"source": PDF_PATH})

    # Chunking
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=3000,
        chunk_overlap=300,
        separators=["\nArt. ", "\n§ ", "\n\n", ". ", " ", ""],
        is_separator_regex=False
    )
    
    splits = text_splitter.split_documents([cleaned_doc])
    print(f"   Utworzono {len(splits)} fragmentów.")

    # --- NOWA LOGIKA: WYSYŁANIE PARTIAMI (BATCHING) ---
    print(f"--- 2. Generowanie wektorów (z opóźnieniem dla darmowego limitu) ---")
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    
    # Tworzymy pustą bazę na dysku
    vectorstore = Chroma(
        persist_directory=DB_PATH, 
        embedding_function=embeddings
    )

    # Ustawienia batchowania
    BATCH_SIZE = 5      # Przetwarzaj po 5 fragmentów na raz
    SLEEP_TIME = 4      # Czekaj 4 sekundy między paczkami (bezpieczny margines)
    
    total_batches = len(splits) // BATCH_SIZE + 1
    
    print(f"   Rozpoczynam wysyłanie {len(splits)} fragmentów w paczkach po {BATCH_SIZE}...")

    for i in range(0, len(splits), BATCH_SIZE):
        batch = splits[i:i + BATCH_SIZE]
        
        # Pasek postępu w konsoli
        current_batch = i // BATCH_SIZE + 1
        print(f"   📤 Paczka {current_batch}/{total_batches} (fragmenty {i}-{min(i+BATCH_SIZE, len(splits))})... ", end="", flush=True)
        
        try:
            # Dodaj dokumenty do bazy
            vectorstore.add_documents(batch)
            print("OK. Czekam...", end="", flush=True)
            
            # Pauza dla API Google (żeby nie dostać błędu 429)
            time.sleep(SLEEP_TIME)
            print(" ✅")
            
        except Exception as e:
            print(f"\n❌ Błąd przy paczce {current_batch}: {e}")
            print("Zatrzymuję proces. Spróbuj zwiększyć SLEEP_TIME.")
            return None

    print("✅ Baza danych utworzona pomyślnie!")
    return vectorstore

# ==========================================
# 3. GŁÓWNA PĘTLA
# ==========================================
def main():
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    
    # Sprawdzamy czy baza istnieje i ma pliki
    if os.path.exists(DB_PATH) and os.listdir(DB_PATH):
        # Opcjonalne: Sprawdź czy baza nie jest pusta (np. po błędzie)
        try:
            vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
            # Próbny odczyt, żeby zobaczyć czy działa
            if vectorstore._collection.count() == 0:
                print("⚠️ Wykryto pustą bazę (poprzedni błąd?). Tworzę od nowa...")
                vectorstore = prepare_database()
        except:
            vectorstore = prepare_database()
    else:
        vectorstore = prepare_database()

    if not vectorstore: return

    # LLM
    try:
        llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    except Exception as e:
        print(f"Błąd modelu: {e}")
        return

    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 5})

    system_prompt = (
        "Jesteś precyzyjnym asystentem prawnym ds. polskiego Kodeksu Pracy. "
        "Twoim zadaniem jest odpowiadanie na pytania, analizując poniższe fragmenty ustawy.\n"
        "ZASADY:\n"
        "1. Używaj procesu myślowego, aby połączyć fakty z różnych artykułów.\n"
        "2. Każdą odpowiedź poprzyj konkretną podstawą prawną (np. 'Zgodnie z Art. 151 § 1...').\n"
        "3. Jeśli w dostarczonym kontekście nie ma odpowiedzi, napisz: 'Niestety, ten fragment Kodeksu Pracy nie porusza tego zagadnienia'.\n"
        "\nKONTEKST PRAWNY:\n"
        "{context}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

    print("\n" + "="*60)
    print(f"   ASYSTENT PRAWNY (Model: {LLM_MODEL} | Emb: {EMBEDDING_MODEL})")
    print("="*60)

    while True:
        query = input("\nTwoje pytanie (wpisz 'exit' by wyjść): ")
        if query.lower() in ['exit', 'quit']: break
        
        print("⏳ Analizuję...")
        try:
            response = rag_chain.invoke({"input": query})
            print(f"\n📝 ODPOWIEDŹ:\n{response['answer']}")
        except Exception as e:
            print(f"Błąd: {e}")

if __name__ == "__main__":
    main()