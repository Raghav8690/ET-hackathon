import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Send, FileText, Settings2, User, Bot, AlertCircle } from 'lucide-react';
import './App.css';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('technical');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(`session-${crypto.randomUUID()}`);
  
  const endOfMessagesRef = useRef(null);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;

    const userMsg = { id: Date.now(), role: 'user', content: query };
    setMessages(prev => [...prev, userMsg]);
    setQuery('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMsg.content,
          session_id: sessionId,
          mode: mode,
          filters: {}
        })
      });

      if (!response.ok) {
        throw new Error('API Error');
      }

      const data = await response.json();
      
      const aiMsg = { 
        id: data.id || Date.now(), 
        role: 'assistant', 
        content: data.answer,
        citations: data.citations
      };
      setMessages(prev => [...prev, aiMsg]);
      
    } catch (error) {
      console.error(error);
      const errorMsg = { 
        id: Date.now(), 
        role: 'assistant', 
        content: 'Sorry, I encountered an error while processing your request.',
        isError: true
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Sidebar - Task 3.4.3 */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>IKI Platform</h2>
          <span className="badge">v2.0</span>
        </div>
        
        <div className="sidebar-section">
          <h3>Chat Mode</h3>
          <div className="mode-toggle">
            <button 
              className={`mode-btn ${mode === 'technical' ? 'active' : ''}`}
              onClick={() => setMode('technical')}
            >
              <Settings2 size={16} />
              Technical
            </button>
            <button 
              className={`mode-btn ${mode === 'manager' ? 'active' : ''}`}
              onClick={() => setMode('manager')}
            >
              <FileText size={16} />
              Manager
            </button>
          </div>
        </div>

        <div className="sidebar-section">
          <h3>Recent Sessions</h3>
          <ul className="session-list">
            <li className="active-session">
              <div className="session-dot"></div>
              Current Session
            </li>
            <li className="past-session">Pump Failure Analysis</li>
            <li className="past-session">Safety Compliance Q3</li>
          </ul>
        </div>
      </aside>

      {/* Main Chat Area - Task 3.4.1 */}
      <main className="chat-main">
        <header className="chat-header">
          <h1>Industrial Knowledge Intelligence Assistant</h1>
          <p>Ask questions about maintenance, operations, and equipment logs.</p>
        </header>

        <div className="messages-container">
          {messages.length === 0 && (
            <div className="empty-state">
              <Bot size={48} className="empty-icon" />
              <h3>How can I help you today?</h3>
              <p>Try asking about "bearing failure on Pump P-101" or "monthly maintenance costs".</p>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`message-wrapper ${msg.role}`}>
              <div className="avatar">
                {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
              </div>
              <div className="message-content">
                {msg.isError ? (
                  <div className="error-message">
                    <AlertCircle size={16} /> {msg.content}
                  </div>
                ) : (
                  <div className="markdown-body">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                )}
                
                {/* Citations Overlay - Task 3.4.2 */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="citations-container">
                    <h4>Sources</h4>
                    <div className="citations-list">
                      {msg.citations.map((c, i) => (
                        <div key={i} className="citation-card" title={c.snippet}>
                          <FileText size={14} />
                          <span>{c.document_id}</span>
                          <span className="page-tag">Pg {c.page}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="message-wrapper assistant">
               <div className="avatar"><Bot size={20} /></div>
               <div className="message-content loading-dots">
                 <span></span><span></span><span></span>
               </div>
            </div>
          )}
          <div ref={endOfMessagesRef} />
        </div>

        <form className="chat-input-form" onSubmit={handleSend}>
          <div className="input-wrapper">
            <input 
              type="text" 
              placeholder={`Ask a question in ${mode} mode...`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={isLoading}
            />
            <button type="submit" disabled={!query.trim() || isLoading}>
              <Send size={18} />
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
