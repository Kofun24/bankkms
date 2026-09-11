import { useState, useEffect, useRef } from "react";
import { api } from "../api";
import "../customer-widget.css";

const SESSION_KEY = "bankkms_customer_session";

export default function CustomerChat() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hi! I'm the BankKMS assistant. Ask me about our accounts, products, or how to get started — I'll answer using our official guides.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    async function initSession() {
      const existing = localStorage.getItem(SESSION_KEY);
      if (existing) {
        setSessionId(existing);
        return;
      }
      try {
        const { session_id } = await api.startChatSession();
        localStorage.setItem(SESSION_KEY, session_id);
        setSessionId(session_id);
      } catch (err) {
        setError("Couldn't start a session. Please refresh the page.");
      }
    }
    initSession();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !sessionId || sending) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setSending(true);
    setError("");

    try {
      const res = await api.sendChatMessage(sessionId, text);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: res.message_to_user },
      ]);
    } catch (err) {
      setError(err.message);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: "Sorry, something went wrong on our end. Please try again.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="cw-page">
      <div className="cw-card">
        <div className="cw-header">
          <div className="cw-brand-mark">K</div>
          <div>
            <div className="cw-brand-name">BankKMS Assistant</div>
            <div className="cw-brand-subtitle">
              Answers grounded in our official documentation
            </div>
          </div>
        </div>

        <div className="cw-messages" ref={scrollRef}>
          {messages.map((m, i) => (
            <div key={i} className={`cw-bubble-row ${m.role}`}>
              <div className={`cw-bubble ${m.role}`}>{m.text}</div>
            </div>
          ))}
          {sending && (
            <div className="cw-bubble-row assistant">
              <div className="cw-bubble assistant cw-typing">Thinking…</div>
            </div>
          )}
        </div>

        {error && <div className="cw-error">{error}</div>}

        <form className="cw-input-row" onSubmit={handleSend}>
          <input
            className="cw-input"
            placeholder="Ask about accounts, fees, or how to get started…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!sessionId || sending}
          />
          <button
            className="cw-send"
            type="submit"
            disabled={!sessionId || sending || !input.trim()}
          >
            Send
          </button>
        </form>

        <div className="cw-footer-note">
          Every answer is based on our approved public documentation. For
          account-specific help, please contact your branch.
        </div>
      </div>
    </div>
  );
}
