import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import "../staff-portal.css";

const STAFF_SESSION_KEY = "bankkms_staff_session";
const STAFF_USER_KEY = "bankkms_staff_user";

export default function StaffChat() {
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState(null);
  const [user, setUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    const storedSession = localStorage.getItem(STAFF_SESSION_KEY);
    const storedUser = localStorage.getItem(STAFF_USER_KEY);

    if (!storedSession || !storedUser) {
      navigate("/staff");
      return;
    }

    const parsedUser = JSON.parse(storedUser);
    setSessionId(storedSession);
    setUser(parsedUser);
    setMessages([
      {
        role: "assistant",
        text: `Hi ${parsedUser.username}. You're signed in with ${parsedUser.role} access. Ask me anything within your authorized knowledge base.`,
      },
    ]);
  }, [navigate]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
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
      const res = await api.sendStaffChatMessage(sessionId, text);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: res.message_to_user, status: res.status },
      ]);
    } catch (err) {
      setError(err.message);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "Sorry, something went wrong. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function handleLogout() {
    if (sessionId) {
      try {
        await api.staffLogout(sessionId);
      } catch {
        // ignore, log out client-side regardless
      }
    }
    localStorage.removeItem(STAFF_SESSION_KEY);
    localStorage.removeItem(STAFF_USER_KEY);
    navigate("/staff");
  }

  if (!user) return null;

  return (
    <div className="sp-chat-page">
      <header className="sp-chat-header">
        <div className="sp-header-left">
          <div className="sp-brand-mark small">K</div>
          <div>
            <div className="sp-header-title">BankKMS Staff Portal</div>
            <div className="sp-header-subtitle">
              {user.username} · <span className={`sp-role-tag ${user.role}`}>{user.role}</span> access
            </div>
          </div>
        </div>
        <button className="sp-logout-btn" onClick={handleLogout}>
          Sign out
        </button>
      </header>

      <div className="sp-chat-body">
        <div className="sp-messages" ref={scrollRef}>
          {messages.map((m, i) => (
            <div key={i} className={`sp-bubble-row ${m.role}`}>
              <div className={`sp-bubble ${m.role} ${m.status === "escalated" ? "escalated" : ""} ${m.status === "denied" ? "denied" : ""}`}>
                {m.text}
              </div>
            </div>
          ))}
          {sending && (
            <div className="sp-bubble-row assistant">
              <div className="sp-bubble assistant sp-typing">Thinking…</div>
            </div>
          )}
        </div>

        {error && <div className="sp-chat-error">{error}</div>}

        <form className="sp-input-row" onSubmit={handleSend}>
          <input
            className="sp-chat-input"
            placeholder="Ask a question within your access level…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending}
          />
          <button className="sp-send" type="submit" disabled={sending || !input.trim()}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}