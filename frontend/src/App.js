import './App.css';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';

function App() {
  const [question, setQuestion] = useState('');
  const [log, setLog] = useState([]);

  const ask = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLog((l) => [...l, { role: 'user', text: question }]);
    setQuestion('');
    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
      });
      const { answer } = await res.json();
      setLog((l) => [...l, { role: 'bot', text: answer }]);
    } catch (err) {
      setLog((l) => [...l, { role: 'error', text: err.message }]);
    }
  };

  return (
    <div className="App">
      <header>
        <h1>Recipes Chatbot</h1>
      </header>

      <form className="chat-form" onSubmit={ask}>
        <input
          className="chat-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
        />
        <button className="chat-button" type="submit">Send</button>
      </form>

      <div className="chat-window">
        {log.map((m, i) => (
          <div key={i} className={`chat-message ${m.role}`}>
            <span className="role">
              {m.role === 'user' ? 'You' : m.role === 'bot' ? 'Bot' : 'Error'}
            </span>
            <ReactMarkdown>{m.text}</ReactMarkdown>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;