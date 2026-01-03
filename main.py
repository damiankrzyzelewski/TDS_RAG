import os
import re
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

# 1. Ładowanie zmiennych środowiskowych (API KEY)
load_dotenv()

# Sprawdzenie klucza
if not os.getenv("GOOGLE_API_KEY"):
    print("BŁĄD: Nie znaleziono klucza w pliku .env")
    exit(1)

# Ustawienia plików
PDF_PATH = "Kodeks_pracy.pdf"  # Upewnij się, że nazwa pliku jest identyczna
DB_PATH = "./chroma_db_kp"

def clean_text(text):
    """
    Usuwa nagłówki i stopki typowe dla ustaw sejmowych (ISAP).
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        if "Kancelaria Sejmu" in line: continue
        if re.search(r'\d{4}-\d{2}-\d{2}', line): continue # Daty
        if line.strip().isdigit(): continue # Numery stron
        
        cleaned_lines.append(line)
        
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text) # Usuwa nadmiarowe entery
    return text

def prepare_database():
    print(f"--- Przetwarzanie pliku: {PDF_PATH} ---")
    
    if not os.path.exists(PDF_PATH):
        print(f"BŁĄD: Nie widzę pliku {PDF_PATH} w folderze!")
        return None

    # A. Ładowanie
    loader = PyPDFLoader(PDF_PATH)
    raw_pages = loader.load()
    
    # B. Czyszczenie i scalanie
    full_text = ""
    for page in raw_pages:
        full_text += clean_text(page.page_content) + "\n\n"
    
    cleaned_doc = Document(page_content=full_text, metadata={"source": PDF_PATH})

    # C. Chunking (Logika prawnicza)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=2500,
        chunk_overlap=200,
        separators=["\nArt. ", "\n§ ", "\n\n", ". ", " ", ""],
        is_separator_regex=False
    )
    
    splits = text_splitter.split_documents([cleaned_doc])
    print(f"Podzielono na {len(splits)} fragmentów.")

    # D. Tworzenie bazy wektorowej
    print("--- Generowanie wektorów (to może chwilę potrwać) ---")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    
    vectorstore = Chroma.from_documents(
        documents=splits, 
        embedding=embeddings, 
        persist_directory=DB_PATH
    )
    return vectorstore

def main():
    # Sprawdzamy czy baza już istnieje na dysku
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    
    if os.path.exists(DB_PATH) and os.listdir(DB_PATH):
        print("--- Znaleziono zapisaną bazę, ładowanie... ---")
        vectorstore = Chroma(persist_directory=DB_PATH, embedding_function=embeddings)
    else:
        vectorstore = prepare_database()
        if not vectorstore: return

    # Konfiguracja modelu RAG
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 6})

    system_prompt = (
        "Jesteś prawnikiem-asystentem. Odpowiadasz na pytania dotyczące polskiego Kodeksu Pracy. "
        "Użyj poniższych fragmentów ustawy, aby udzielić precyzyjnej odpowiedzi. "
        "Jeśli fragmenty nie zawierają odpowiedzi, napisz wprost że nie znaleziono odpowiedzi na pytanie w kodeksie pracy. "
        "Zawsze cytuj numery Artykułów (np. Art. 22 § 1), jeśli na nich bazujesz."
        "\n\n"
        "FRAGMENTY USTAWY:\n"
        "{context}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    qa_chain = create_retrieval_chain(retriever, create_stuff_documents_chain(llm, prompt))

    print("\n" + "="*40)
    print("System gotowy. Zadaj pytanie o Kodeks Pracy.")
    print("="*40)

    while True:
        query = input("\nPytanie (wpisz 'exit' by wyjść): ")
        if query.lower() in ['exit', 'quit']: break
        
        result = qa_chain.invoke({"input": query})
        print(f"\nODPOWIEDŹ:\n{result['answer']}")

if __name__ == "__main__":
    main()