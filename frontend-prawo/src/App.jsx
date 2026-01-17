import { useState, useEffect, useRef } from 'react'
import './App.css'

function App() {
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [dbReady, setDbReady] = useState(true)
  const [building, setBuilding] = useState(false)

  const [useContext, setUseContext] = useState(false)

  const chatEndRef = useRef(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    fetch('http://127.0.0.1:8000/status')
      .then(res => res.json())
      .then(data => setDbReady(data.ready))
      .catch(() => setDbReady(false))
  }, [])

  const buildDatabase = async () => {
    setBuilding(true)
    try {
      await fetch('http://127.0.0.1:8000/build', { method: 'POST' })
      setDbReady(true)
    } catch {
      alert("Błąd budowania bazy")
    }
    setBuilding(false)
  }

  const formatText = (text) => {
    if (!text) return "";
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  };

  const sendMessage = async () => {
    if (!query.trim()) return

    const currentHistory = [...messages];
    const newMessages = [...messages, { role: 'user', text: query }]
    setMessages(newMessages)
    setQuery('')
    setLoading(true)

    // Logika wysyłania historii
    let historyPayload = [];
    
    if (useContext) {
      historyPayload = currentHistory.map(msg => ({
        role: msg.role,
        content: msg.text 
      }));
    }

    console.log("Tryb pamięci:", useContext ? "WŁĄCZONY" : "WYŁĄCZONY");

    try {
      const res = await fetch('http://127.0.0.1:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          question: query,
          chat_history: historyPayload
        })
      })

      const data = await res.json()

      setMessages([
        ...newMessages,
        {
          role: 'ai',
          text: data.answer,
          sources: data.sources ? data.sources.filter(src => src && src.trim().length > 0) : []
        }
      ])
    } catch (error) {
      console.error("Błąd:", error);
      setMessages([
        ...newMessages,
        { role: 'ai', text: 'Przepraszam, wystąpił błąd połączenia z serwerem.' }
      ])
    }

    setLoading(false)
  }

  return (
    <div className="container">
      <header>
        <h1>⚖️ Asystent Prawa Pracy</h1>

        {/* PRZEŁĄCZNIK TRYBU Z TOOLTIPEM */}
        <div className="mode-toggle">
          <div className="tooltip-container">
            <span className="label-text">🧠 Pamięć rozmowy: {useContext ? 'WŁ' : 'WYŁ'}</span>
            
            {/* TREŚĆ DYMKA */}
            <div className="tooltip-box">
              <strong>Włączone:</strong> Bot pamięta kontekst poprzednich pytań.<br/>
              <span style={{color: '#fbbf24'}}>⚠️ Uwaga: Zwiększa zużycie tokenów (koszt).</span>
            </div>
          </div>

          <label className="switch">
            <input 
              type="checkbox" 
              checked={useContext} 
              onChange={(e) => setUseContext(e.target.checked)} 
            />
            <span className="slider"></span>
          </label>
        </div>
        
        {!dbReady && (
          <div className="warning">
            <span>⚠️ Baza wiedzy nie jest gotowa.</span>
            <button onClick={buildDatabase} disabled={building}>
              {building ? 'Budowanie...' : 'Zbuduj bazę'}
            </button>
          </div>
        )}
      </header>

      <div className="chat-window">
        {messages.length === 0 && (
          <div style={{
              display: 'flex', 
              flexDirection: 'column', 
              alignItems: 'center', 
              justifyContent: 'center', 
              height: '100%', 
              color: 'var(--text-muted)',
              textAlign: 'center'
            }}>
            <p style={{fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '10px'}}>Witaj!</p>
            <p>Jestem tutaj, aby pomóc Ci w kwestiach prawa pracy.</p>
            <small style={{marginTop: '20px', opacity: 0.7}}>Zadaj pytanie, np. "Czy urlop przepada?"</small>
          </div>
        )}

        {messages.map((msg, idx) => {
          const cleanSources = msg.sources || [];
          return (
            <div key={idx} className={`message-row ${msg.role}`}>
              <div className="avatar">
                {msg.role === 'user' ? '👤' : '⚖️'}
              </div>
              
              <div className={`message ${msg.role}`}>
                <div className="content">
                  {msg.role === 'ai' ? formatText(msg.text) : msg.text}
                </div>
                
                {msg.role === 'ai' && cleanSources.length > 0 && (
                  <details className="sources">
                    <summary>📚 Podstawa prawna (rozwiń)</summary>
                    <ul>
                      {cleanSources.map((src, i) => (
                        <li key={i}>{src}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="message-row ai">
            <div className="avatar">⚖️</div>
            <div className="message ai">
              <div className="typing-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      <div className="input-area">
        <input 
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
          placeholder="Napisz pytanie..."
          disabled={!dbReady || loading}
        />
        <button onClick={sendMessage} disabled={!dbReady || loading}>
          Wyślij
        </button>
      </div>
    </div>
  )
}

export default App
