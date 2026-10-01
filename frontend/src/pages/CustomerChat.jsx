import { useState, useEffect, useRef } from "react";
import { api } from "../api";

const CUSTOMER_SESSION_KEY = "bankkms_customer_session";

const SAMPLE_PROMPTS = [
  "What documents do I need to open a savings account?",
  "What are the valid forms of identification for KYC verification?",
  "What is the minimum balance required to avoid monthly account fees?",
  "What are my rights regarding unauthorized transaction dispute timeframes?",
];

export default function CustomerChat() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    async function initSession() {
      const existing = sessionStorage.getItem(CUSTOMER_SESSION_KEY);
      if (existing) {
        setSessionId(existing);
        return;
      }
      try {
        const { session_id } = await api.startChatSession();
        sessionStorage.setItem(CUSTOMER_SESSION_KEY, session_id);
        setSessionId(session_id);
      } catch {
        setError("Unable to initialize secure session. Please refresh the page.");
      }
    }
    initSession();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, sending]);

  async function startNewSession() {
    sessionStorage.removeItem(CUSTOMER_SESSION_KEY);
    setMessages([]);
    setError("");
    try {
      const { session_id } = await api.startChatSession();
      sessionStorage.setItem(CUSTOMER_SESSION_KEY, session_id);
      setSessionId(session_id);
    } catch {
      setError("Unable to start a new session. Please refresh.");
    }
  }

  async function handleSend(queryText) {
    const text = (queryText || input).trim();
    if (!text || !sessionId || sending) return;

    const userMessage = {
      role: "user",
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setSending(true);
    setError("");

    try {
      const res = await api.sendChatMessage(sessionId, text);
      const assistantMessage = {
        role: "assistant",
        status: res.status || "answered",
        text: res.message_to_user,
        final_response: res.final_response,
        denial_reason: res.denial_reason,
        needs_clarification: res.needs_clarification,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err.message || "Request failed. Please try again.");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          status: "escalated",
          text: "We encountered a network or service issue while processing your question. Please try asking again.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    handleSend();
  }

  return (
    <div className="bk-customer-surface">
      {/* Institutional Top Masthead */}
      <header className="bk-customer-masthead">
        <div className="bk-masthead-inner">
          <div className="bk-masthead-brand">
            <span className="bk-masthead-logo">BankKMS</span>
            <span className="bk-masthead-divider">/</span>
            <span className="bk-masthead-sub">Customer Knowledge Base</span>
          </div>

          <div className="bk-masthead-meta">
            <div className="bk-scope-tag public">
              <span className="bk-scope-indicator"></span>
              <span>Scope: Public Documentation</span>
            </div>
            <button
              type="button"
              className="bk-btn-text"
              onClick={startNewSession}
              title="Clear current conversation and request a fresh session token"
            >
              New Session
            </button>
          </div>
        </div>
      </header>

      {/* Main Conversation & Sourcing Viewport */}
      <main className="bk-customer-body">
        <div className="bk-customer-container">
          <div className="bk-customer-intro-bar">
            <h1>Official Banking Information &amp; Policy Assistance</h1>
            <p>
              Every response is grounded in approved BankKMS public documentation. Unverified
              claims and speculative answers are strictly prohibited by our governance pipeline.
            </p>
          </div>

          {/* Conversation Stream */}
          <div className="bk-customer-stream" ref={scrollRef}>
            {messages.length === 0 ? (
              <div className="bk-empty-stream-card">
                <div className="bk-empty-stream-header">
                  <h2>How can we help you today?</h2>
                  <p>
                    Select a frequently referenced policy below, or enter your question directly.
                  </p>
                </div>
                <div className="bk-prompt-chips">
                  {SAMPLE_PROMPTS.map((prompt, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="bk-prompt-chip"
                      onClick={() => handleSend(prompt)}
                      disabled={sending || !sessionId}
                    >
                      <span>{prompt}</span>
                    </button>
                  ))}
                </div>
                <div className="bk-empty-stream-footer">
                  <p>
                    Documents in scope: <strong>Savings Account Guide</strong>,{" "}
                    <strong>Current Account Guide</strong>, <strong>KYC Requirements</strong>, and{" "}
                    <strong>Customer Rights Charter</strong>.
                  </p>
                </div>
              </div>
            ) : (
              messages.map((msg, index) => (
                <div key={index} className={`bk-stream-row ${msg.role}`}>
                  {msg.role === "user" ? (
                    <div className="bk-user-bubble">
                      <div className="bk-user-header">
                        <span className="bk-sender-label">Your Question</span>
                        <span className="bk-msg-time">{msg.timestamp}</span>
                      </div>
                      <div className="bk-user-text">{msg.text}</div>
                    </div>
                  ) : (
                    <AssistantResponseCard message={msg} />
                  )}
                </div>
              ))
            )}

            {sending && (
              <div className="bk-stream-row assistant">
                <div className="bk-typing-indicator" aria-label="Thinking">
                  <span className="bk-typing-dot"></span>
                  <span className="bk-typing-dot"></span>
                  <span className="bk-typing-dot"></span>
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="bk-alert-banner" role="alert">
              <span>{error}</span>
            </div>
          )}

          {/* Prompt Entry Form */}
          <form className="bk-customer-input-area" onSubmit={handleSubmit}>
            <div className="bk-input-wrapper">
              <label htmlFor="customer-query-input" className="sr-only">
                Ask a banking question
              </label>
              <input
                id="customer-query-input"
                className="bk-customer-input"
                type="text"
                placeholder="Ask about opening accounts, required KYC documents, or minimum balance rules…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={sending || !sessionId}
                autoComplete="off"
              />
              <button
                type="submit"
                className="bk-customer-submit"
                disabled={sending || !sessionId || !input.trim()}
              >
                {sending ? "Sending…" : "Submit Question"}
              </button>
            </div>
            <div className="bk-input-footnote">
              <span>
                Anonymous visitor session ({sessionId ? sessionId.slice(0, 8) : "connecting…"}
                ). Session history is not stored across visits.
              </span>
              <a href="/staff" className="bk-footnote-link">
                Staff Portal
              </a>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}

/**
 * Explicit visual treatments for the 4 pipeline statuses:
 * - "answered"
 * - "needs_clarification"
 * - "denied"
 * - "escalated"
 */
function AssistantResponseCard({ message }) {
  const { status, text, final_response, timestamp } = message;

  // Extract citations if present
  const citations =
    final_response?.citations && final_response.citations.length > 0
      ? final_response.citations
      : [];

  // Determine sub-type for denied (access-related vs ungrounded)
  const isAccessDenial =
    status === "denied" &&
    (text.toLowerCase().includes("access") ||
      text.toLowerCase().includes("restricted") ||
      text.toLowerCase().includes("internal"));

  return (
    <article className={`bk-response-card status-${status}`}>
      {/* 1. STATUS: ANSWERED */}
      {status === "answered" && (
        <>
          <div className="bk-card-header answered">
            <div className="bk-status-indicator">
              <span className="bk-status-pill answered">Verified &amp; Grounded</span>
              <span className="bk-status-caption">Sourced from Official Documentation</span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-card-body">
            <div className="bk-answer-text">{text}</div>

            {/* Citations as first-class UI elements with proper typographic weight */}
            {citations.length > 0 && (
              <section className="bk-citations-section">
                <h3 className="bk-citations-heading">Cited Knowledge Sources</h3>
                <div className="bk-citations-grid">
                  {citations.map((cite, idx) => (
                    <div key={idx} className="bk-citation-item">
                      <div className="bk-citation-top">
                        <span className="bk-citation-doc">{cite.doc_title}</span>
                        {cite.doc_id && (
                          <span className="bk-citation-id tabular-nums">{cite.doc_id}</span>
                        )}
                      </div>
                      <div className="bk-citation-meta">
                        <span className="bk-citation-section">{cite.section}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </>
      )}

      {/* 2. STATUS: NEEDS CLARIFICATION */}
      {status === "needs_clarification" && (
        <>
          <div className="bk-card-header clarify">
            <div className="bk-status-indicator">
              <span className="bk-status-pill clarify">Clarification Requested</span>
              <span className="bk-status-caption">More detail required to locate source</span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-card-body">
            <div className="bk-clarify-callout">
              <p className="bk-clarify-prompt">{text}</p>
              <p className="bk-clarify-hint">
                Please reply with additional details or specify which product or transaction type
                you are referring to.
              </p>
            </div>
          </div>
        </>
      )}

      {/* 3. STATUS: DENIED (Access boundary or No reliable info) */}
      {status === "denied" && (
        <>
          <div className="bk-card-header denied">
            <div className="bk-status-indicator">
              <span className="bk-status-pill denied">
                {isAccessDenial ? "Access Boundary Enforced" : "Information Not Available"}
              </span>
              <span className="bk-status-caption">
                {isAccessDenial
                  ? "Requires authorized internal staff credentials"
                  : "Not found in approved public guides"}
              </span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-card-body">
            <div className="bk-denied-callout">
              <p className="bk-denied-reason">{text}</p>
              <div className="bk-denied-guidance">
                {isAccessDenial ? (
                  <p>
                    If you are an employee or compliance officer seeking internal procedures,
                    please sign in through the <a href="/staff">BankKMS Staff Portal</a>.
                  </p>
                ) : (
                  <p>
                    For specific account assistance, please contact your nearest branch or official
                    customer telephone banking representative.
                  </p>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* 4. STATUS: ESCALATED */}
      {status === "escalated" && (
        <>
          <div className="bk-card-header escalated">
            <div className="bk-status-indicator">
              <span className="bk-status-pill escalated">Escalated for Human Review</span>
              <span className="bk-status-caption">Flagged to prevent unverified guidance</span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-card-body">
            <div className="bk-escalated-callout">
              <p className="bk-escalated-reason">{text}</p>
              <div className="bk-escalated-notes">
                <p>
                  <strong>Why was this escalated?</strong> The BankKMS governance pipeline routes
                  inquiries to specialist staff when documentation confidence is low or when
                  conflicting policy rules are detected.
                </p>
                <p>
                  Branch assistance desk: <strong>1-800-BANK-KMS</strong> (Mon–Fri 08:00–17:00).
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </article>
  );
}
