import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [dbReady, setDbReady] = useState(true)
  const [building, setBuilding] = useState(false)

  // Sprawdź status bazy przy starcie
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
    } catch (e) {
      alert("Błąd budowania bazy")
    }
    setBuilding(false)
  }

  const sendMessage = async () => {
    if (!query.trim()) return

    const newMessages = [...messages, { role: 'user', text: query }]
    setMessages(newMessages)
    setQuery('')
    setLoading(true)

    try {
      const res = await fetch('http://127.0.0.1:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query })
      })
      
      const data = await res.json()
      setMessages([...newMessages, { 
        role: 'ai', 
        text: data.answer, 
        sources: data.sources 
      }])
    } catch (e) {
      setMessages([...newMessages, { role: 'ai', text: "Błąd połączenia z serwerem." }])
    }
    setLoading(false)
  }

  return (
    <div className="container">
      <header>
        <h1>⚖️ Asystent Prawa Pracy</h1>
        {!dbReady && (
          <div className="warning">
            <p>Baza wiedzy nie istnieje!</p>
            <button onClick={buildDatabase} disabled={building}>
              {building ? "Budowanie bazy (to potrwa 15 min)..." : "Zbuduj Bazę"}
            </button>
          </div>
        )}
      </header>

      <div className="chat-window">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="content">{msg.text}</div>
            {msg.sources && (
              <details>
                <summary>Pokaż źródła prawne</summary>
                <ul>
                  {msg.sources.map((src, i) => <li key={i}>{src}</li>)}
                </ul>
              </details>
            )}
          </div>
        ))}
        {loading && <div className="message ai"><div className="content">⏳ Analizuję przepisy...</div></div>}
      </div>

      <div className="input-area">
        <input 
          value={query} 
          onChange={e => setQuery(e.target.value)}
          onKeyPress={e => e.key === 'Enter' && sendMessage()}
          placeholder="Zadaj pytanie (np. Czy urlop przechodzi na kolejny rok?)..."
          disabled={!dbReady || loading}
        />
        <button onClick={sendMessage} disabled={!dbReady || loading}>Wyślij</button>
      </div>
    </div>
  )
}

export default App