# Asystent Prawa Pracy (RAG)

Aplikacja wykorzystująca sztuczną inteligencję do analizy i interpretacji polskiego Kodeksu Pracy. Projekt działa w architekturze **Client-Server** (React + Python) i wykorzystuje technikę **RAG** (Retrieval-Augmented Generation), aby udzielać precyzyjnych odpowiedzi wraz z cytowaniem podstawy prawnej.

## Wykorzystane Modele AI
* **Wnioskowanie:** Google Gemini 2.5 Flash (model z procesem myślowym "Thinking").
* **Wektoryzacja (Embeddings):** Google Gemini Embedding 001.

## Technologia
* **Backend:** Python 3.10+, FastAPI, Uvicorn, LangChain, ChromaDB.
* **Frontend:** React, Vite, Node.js.

---

## Wymagania wstępne

Przed uruchomieniem upewnij się, że posiadasz:
1.  **Python** (wersja 3.10 lub nowsza).
2.  **Node.js** (wersja LTS, do obsługi interfejsu).
3.  **Klucz API Google** (do pobrania z [Google AI Studio](https://aistudio.google.com/)).

---

## Instalacja i Uruchomienie

Projekt wymaga uruchomienia dwóch niezależnych procesów: serwera backendowego oraz interfejsu frontendowego.

### KROK 1: Konfiguracja Backendu (API)

1.  Otwórz terminal w **głównym folderze projektu**.
2.  Zainstaluj wymagane biblioteki z pliku `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```
3.  Utwórz plik `.env` w głównym folderze i wklej swój klucz API:
    ```env
    GOOGLE_API_KEY=TwojKluczTutaj
    ```
4.  Upewnij się, że plik `Kodeks_pracy.pdf` znajduje się w tym samym folderze.
5.  Uruchom serwer API:
    ```bash
    uvicorn api:app --reload
    ```
   *Backend powinien działać pod adresem: `http://127.0.0.1:8000`*

### KROK 2: Konfiguracja Frontendu (Interfejs)

1.  Otwórz **drugie okno terminala**.
2.  Wejdź do folderu z aplikacją React:
    ```bash
    cd frontend-prawo
    ```
3.  Zainstaluj zależności (tylko przy pierwszym uruchomieniu):
    ```bash
    npm install
    ```
4.  Uruchom aplikację:
    ```bash
    npm run dev
    ```
   *Aplikacja otworzy się pod adresem: `http://localhost:5173`*

---

## Pierwsze użycie (Budowanie Bazy Wiedzy)

1.  Otwórz aplikację w przeglądarce (`http://localhost:5173`).
2.  Jeśli uruchamiasz projekt po raz pierwszy (lub usunąłeś folder bazy), zobaczysz komunikat o braku bazy i przycisk **"Zbuduj Bazę"**.
3.  Kliknij przycisk. System rozpocznie proces:
    * Wczytania pliku PDF.
    * Podziału na artykuły prawne.
    * Generowania wektorów (embeddingów).
4.  **Czas trwania:** ok. 10-15 minut.
    * *Uwaga:* Aplikacja posiada zabezpieczenie – jeśli przekroczysz darmowy limit zapytań Google (błąd 429), backend automatycznie wstrzyma pracę na 60 sekund i wznowi ją samoczynnie.
5.  Po zakończeniu procesu możesz rozpocząć czat z asystentem.

---


## Struktura projektu

* `api.py` – Główny kod serwera (FastAPI + LangChain).
* `requirements.txt` – Lista wymaganych bibliotek Python.
* `Kodeks_pracy.pdf` – Plik źródłowy.
* `.env` – Plik z kluczem API (nieudostępniany publicznie).
* `chroma_db_kp/` – Folder z bazą wektorową (tworzony automatycznie).
* `frontend-prawo/` – Kod źródłowy aplikacji React.
