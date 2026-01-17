import os
import re
import sys
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

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    print("BŁĄD: Nie znaleziono klucza GOOGLE_API_KEY w pliku .env")
    sys.exit(1)

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
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def prepare_database():
    print(f"--- 1. Przetwarzanie pliku: {PDF_PATH} ---")
    
    if not os.path.exists(PDF_PATH):
        print(f"BŁĄD: Nie widzę pliku {PDF_PATH} w folderze!")
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

    print(f"--- 2. Generowanie wektorów (Tryb bezpieczny) ---")
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    
    vectorstore = Chroma(
        persist_directory=DB_PATH, 
        embedding_function=embeddings
    )

    # ZMIANA: Wysyłamy po 1 dokumencie, żeby kontrolować błędy
    BATCH_SIZE = 1      
    total = len(splits)
    
    print(f"   Rozpoczynam wysyłanie {total} fragmentów...")

    for i, doc in enumerate(splits):
        # Pętla nieskończona dla JEDNEGO dokumentu - dopóki nie przejdzie
        while True:
            try:
                # Próba dodania
                print(f"   Fragment {i+1}/{total}... ", end="", flush=True)
                vectorstore.add_documents([doc])
                
                # Sukces? Krótka przerwa i idziemy dalej
                print("OK")
                time.sleep(1.5) # 1.5 sekundy przerwy między każdym zapytaniem
                break 

            except Exception as e:
                # Jeśli błąd zawiera "429" lub "ResourceExhausted"
                error_msg = str(e)
                if "429" in error_msg or "ResourceExhausted" in error_msg:
                    print(f"\n   LIMIT PRZEKROCZONY (Błąd 429).")
                    print("   Czekam 60 sekund na reset licznika Google...")
                    time.sleep(60)
                    print("   Wznawiam próbę dla tego samego fragmentu...")
                else:
                    # Inny błąd (np. brak neta) - też czekamy, ale krócej
                    print(f"\n   Inny błąd: {e}")
                    print("   Czekam 10 sekund i próbuję ponownie...")
                    time.sleep(10)

    print("\nBaza danych utworzona pomyślnie i zapisana!")
    return vectorstore

def main():
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    
    if os.path.exists(DB_PATH) and os.listdir(DB_PATH):
        try:
            vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
            if vectorstore._collection.count() == 0:
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
        
        print("Analizuję...")
        try:
            response = rag_chain.invoke({"input": query})
            print(f"\n ODPOWIEDŹ:\n{response['answer']}")
        except Exception as e:
            print(f"Błąd: {e}")

if __name__ == "__main__":
    main()
