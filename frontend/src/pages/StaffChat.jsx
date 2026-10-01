import { useState, useEffect, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const STAFF_SESSION_KEY = "bankkms_staff_session";
const STAFF_USER_KEY = "bankkms_staff_user";

function getStorageHistoryKey(username) {
  return `bankkms_staff_threads_${username || "unknown"}`;
}

function createDefaultThread(user) {
  const now = new Date();
  return {
    id: `thread_${Date.now()}`,
    title: "New Consultation",
    createdAt: now.toISOString(),
    updatedAt: now.toISOString(),
    messages: [
      {
        role: "assistant",
        status: "answered",
        text: `Welcome, ${user?.username || "Staff"}. Your session is initialized with ${user?.access_level?.toUpperCase() || "INTERNAL"} access tier (${user?.role?.toUpperCase() || "EMPLOYEE"} role). All queries are verified against authorized knowledge boundaries and recorded in the immutable audit log.`,
        timestamp: now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ],
  };
}

function loadInitialThreads(user) {
  if (!user?.username) return [];
  try {
    const saved = localStorage.getItem(getStorageHistoryKey(user.username));
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    // fallback
  }
  return [createDefaultThread(user)];
}

export default function StaffChat() {
  const navigate = useNavigate();
  const [sessionId] = useState(() => localStorage.getItem(STAFF_SESSION_KEY));
  const [user] = useState(() => {
    const raw = localStorage.getItem(STAFF_USER_KEY);
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  // Chat history threads state (only for logged-in accounts)
  const [threads, setThreads] = useState(() => loadInitialThreads(user));

  const [activeThreadId, setActiveThreadId] = useState(() => {
    const initial = loadInitialThreads(user);
    return initial[0]?.id || null;
  });

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!sessionId || !user) {
      navigate("/staff");
    }
  }, [sessionId, user, navigate]);

  const activeThread = useMemo(() => {
    return threads.find((t) => t.id === activeThreadId) || threads[0] || null;
  }, [threads, activeThreadId]);

  const messages = useMemo(() => {
    return activeThread ? activeThread.messages : [];
  }, [activeThread]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, sending]);

  function persistThreads(updated) {
    setThreads(updated);
    if (user?.username) {
      try {
        localStorage.setItem(getStorageHistoryKey(user.username), JSON.stringify(updated));
      } catch {
        // quota limit or disabled
      }
    }
  }

  function handleNewChat() {
    if (!user) return;
    const newThread = createDefaultThread(user);
    const updated = [newThread, ...threads];
    persistThreads(updated);
    setActiveThreadId(newThread.id);
    setError("");
  }

  function handleDeleteThread(threadId, e) {
    e.stopPropagation();
    const updated = threads.filter((t) => t.id !== threadId);
    if (updated.length === 0 && user) {
      const fallback = createDefaultThread(user);
      persistThreads([fallback]);
      setActiveThreadId(fallback.id);
    } else {
      persistThreads(updated);
      if (activeThreadId === threadId) {
        setActiveThreadId(updated[0].id);
      }
    }
  }

  function handleClearAllHistory() {
    if (!user) return;
    const fresh = createDefaultThread(user);
    persistThreads([fresh]);
    setActiveThreadId(fresh.id);
  }

  async function handleSend(queryText) {
    const text = (queryText || input).trim();
    if (!text || !sessionId || sending || !activeThread) return;

    const userMessage = {
      role: "user",
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    // Update active thread with user message immediately
    const nowIso = new Date().toISOString();
    const updatedWithUser = threads.map((t) => {
      if (t.id === activeThread.id) {
        const isDefaultTitle = t.title === "New Consultation" || t.messages.length <= 1;
        const newTitle = isDefaultTitle
          ? text.slice(0, 38) + (text.length > 38 ? "…" : "")
          : t.title;
        return {
          ...t,
          title: newTitle,
          updatedAt: nowIso,
          messages: [...t.messages, userMessage],
        };
      }
      return t;
    });

    persistThreads(updatedWithUser);
    setInput("");
    setSending(true);
    setError("");

    try {
      const res = await api.sendStaffChatMessage(sessionId, text);
      const assistantMessage = {
        role: "assistant",
        status: res.status || "answered",
        text: res.message_to_user,
        final_response: res.final_response,
        version_conflict_detected: res.version_conflict_detected,
        denial_reason: res.denial_reason,
        needs_clarification: res.needs_clarification,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      const updatedWithAssistant = updatedWithUser.map((t) => {
        if (t.id === activeThread.id) {
          return {
            ...t,
            updatedAt: new Date().toISOString(),
            messages: [...t.messages, assistantMessage],
          };
        }
        return t;
      });

      persistThreads(updatedWithAssistant);
    } catch (err) {
      setError(err.message || "Failed to execute query.");
      const errorMessage = {
        role: "assistant",
        status: "escalated",
        text: "System communication error occurred during query evaluation. Please retry.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      const updatedWithError = updatedWithUser.map((t) => {
        if (t.id === activeThread.id) {
          return {
            ...t,
            updatedAt: new Date().toISOString(),
            messages: [...t.messages, errorMessage],
          };
        }
        return t;
      });

      persistThreads(updatedWithError);
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    handleSend();
  }

  async function handleLogout() {
    if (sessionId) {
      try {
        await api.staffLogout(sessionId);
      } catch {
        // Log out client-side regardless
      }
    }
    localStorage.removeItem(STAFF_SESSION_KEY);
    localStorage.removeItem(STAFF_USER_KEY);
    navigate("/staff");
  }

  if (!user) return null;

  const isCompliance = user.role === "compliance";
  const tierClass = isCompliance ? "restricted" : "internal";

  const sampleQuestions = isCompliance
    ? [
        "What is the SAR filing threshold and mandatory escalation protocol?",
        "What are the documentation standards for fraud investigation case closure?",
        "What are the enhanced due diligence triggers for politically exposed persons?",
      ]
    : [
        "What is the step-by-step account opening procedure for high net worth clients?",
        "What is the mandatory timeline for resolving customer fee complaints?",
        "What are the identity verification procedures for non-resident retail accounts?",
      ];

  return (
    <div className="bk-staff-workspace">
      {/* Top Header */}
      <header className="bk-staff-header">
        <div className="bk-staff-header-left">
          <div className="bk-staff-logo">BankKMS</div>
          <span className="bk-staff-divider">/</span>
          <span className="bk-staff-portal-title">Staff Knowledge Portal</span>
        </div>

        <div className="bk-staff-header-right">
          <button
            type="button"
            className="bk-btn-secondary bk-history-toggle-btn"
            onClick={() => setSidebarOpen((prev) => !prev)}
            title="Toggle Chat History"
          >
            {sidebarOpen ? "Hide History" : "Chat History"}
          </button>
          <div className="bk-user-credential-pill">
            <span className="bk-user-name">{user.username}</span>
            <span className={`bk-role-tag ${user.role}`}>{user.role}</span>
          </div>
          <button type="button" className="bk-btn-secondary" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </header>

      {/* Trust Ladder Structural Signal Banner */}
      <div className={`bk-trust-ladder-banner ${tierClass}`}>
        <div className="bk-trust-ladder-content">
          <div className="bk-tier-title-row">
            <span className={`bk-tier-badge ${tierClass}`}>
              Access Tier: {user.access_level.toUpperCase()}
            </span>
            <span className="bk-tier-role-desc">
              Enforced at Retrieval &amp; Verification Stages
            </span>
          </div>
          <p className="bk-tier-scope-summary">
            {isCompliance
              ? "Scope: Complete institutional repository including Restricted AML directives, SAR protocols, fraud investigation guidelines, internal procedures, and public customer documentation."
              : "Scope: Internal operational procedures, account opening workflows, customer service manuals, and public documentation. Restricted compliance policies are withheld."}
          </p>
        </div>
      </div>

      {/* Main Layout: History Sidebar (for logged-in accounts) + Chat Area */}
      <div className="bk-staff-layout">
        {/* Chat History Sidebar — Dedicated to Logged-in Staff Accounts */}
        {sidebarOpen && (
          <aside className="bk-staff-history-sidebar" aria-label="Staff Chat History">
            <div className="bk-history-sidebar-header">
              <button
                type="button"
                className="bk-btn-primary full-width"
                onClick={handleNewChat}
              >
                + New Chat
              </button>
            </div>

            <div className="bk-history-section-title">
              <span>Saved Consultations ({threads.length})</span>
            </div>

            <div className="bk-history-thread-list">
              {threads.map((thread) => {
                const isActive = thread.id === activeThreadId;
                const queryCount = thread.messages.filter((m) => m.role === "user").length;
                const formattedDate = new Date(thread.updatedAt || thread.createdAt).toLocaleDateString([], {
                  month: "short",
                  day: "numeric",
                });

                return (
                  <div
                    key={thread.id}
                    className={`bk-history-item ${isActive ? "active" : ""}`}
                    onClick={() => setActiveThreadId(thread.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        setActiveThreadId(thread.id);
                      }
                    }}
                  >
                    <div className="bk-history-item-main">
                      <span className="bk-history-item-title">{thread.title}</span>
                      <div className="bk-history-item-meta tabular-nums">
                        <span>{formattedDate}</span>
                        <span>·</span>
                        <span>{queryCount} {queryCount === 1 ? "query" : "queries"}</span>
                      </div>
                    </div>
                    {threads.length > 1 && (
                      <button
                        type="button"
                        className="bk-history-item-del"
                        onClick={(e) => handleDeleteThread(thread.id, e)}
                        title="Delete consultation thread"
                        aria-label={`Delete thread ${thread.title}`}
                      >
                        ×
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="bk-history-sidebar-footer">
              <button
                type="button"
                className="bk-btn-text full-width"
                onClick={handleClearAllHistory}
                title="Clear all saved consultations for this account"
              >
                Clear History
              </button>
            </div>
          </aside>
        )}

        {/* Active Chat Main Area */}
        <main className="bk-staff-main">
          <div className="bk-staff-container">
            <div className="bk-staff-messages" ref={scrollRef}>
              {messages.map((msg, index) => (
                <div key={index} className={`bk-staff-msg-row ${msg.role}`}>
                  {msg.role === "user" ? (
                    <div className="bk-staff-user-bubble">
                      <div className="bk-user-meta">
                        <span className="bk-msg-author">{user.username} (Query)</span>
                        <time className="bk-msg-time">{msg.timestamp}</time>
                      </div>
                      <div className="bk-msg-content">{msg.text}</div>
                    </div>
                  ) : (
                    <StaffResponseCard message={msg} role={user.role} />
                  )}
                </div>
              ))}

              {/* Quiet Answering Indicator — NO "in-process" text */}
              {sending && (
                <div className="bk-staff-msg-row assistant">
                  <div className="bk-typing-indicator" aria-label="Thinking">
                    <span className="bk-typing-dot"></span>
                    <span className="bk-typing-dot"></span>
                    <span className="bk-typing-dot"></span>
                  </div>
                </div>
              )}
            </div>

            {/* Quick Prompt Suggestions */}
            <div className="bk-staff-quick-prompts">
              <span className="bk-quick-label">Authorized Query Suggestions:</span>
              <div className="bk-quick-list">
                {sampleQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="bk-quick-btn"
                    onClick={() => handleSend(q)}
                    disabled={sending}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="bk-alert-banner" role="alert">
                <span>{error}</span>
              </div>
            )}

            {/* Query Input Bar */}
            <form className="bk-staff-input-form" onSubmit={handleSubmit}>
              <div className="bk-staff-input-wrapper">
                <label htmlFor="staff-query-input" className="sr-only">
                  Ask a staff query
                </label>
                <input
                  id="staff-query-input"
                  className="bk-staff-input"
                  type="text"
                  placeholder={`Ask an authorized ${user.role} question across ${user.access_level} documentation…`}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={sending}
                  autoComplete="off"
                />
                <button
                  type="submit"
                  className="bk-btn-primary"
                  disabled={sending || !input.trim()}
                >
                  {sending ? "Sending…" : "Submit Query"}
                </button>
              </div>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}

/**
 * Detailed Staff Response Card with explicit status handling:
 * - Answered (with detailed version + effective date citations)
 * - Version conflict note (styled as informational notice, not error)
 * - Needs clarification
 * - Denied (access tier boundary)
 * - Escalated (human review)
 */
function StaffResponseCard({ message, role }) {
  const { status, text, final_response, version_conflict_detected, timestamp } = message;

  const citations =
    final_response?.citations && final_response.citations.length > 0
      ? final_response.citations
      : [];

  return (
    <article className={`bk-staff-card status-${status}`}>
      {/* 1. STATUS: ANSWERED */}
      {status === "answered" && (
        <>
          <div className="bk-staff-card-header answered">
            <div className="bk-status-indicator">
              <span className="bk-status-pill answered">Verified &amp; Grounded</span>
              <span className="bk-status-caption">Grounded in official policy</span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-staff-card-body">
            {/* Version conflict note styled as information, NOT an error */}
            {version_conflict_detected && (
              <div className="bk-version-conflict-notice">
                <div className="bk-conflict-icon">i</div>
                <div>
                  <strong>Policy Revision Notice</strong>
                  <p>
                    A superseded version of this document exists on record. The figures and clauses
                    above reflect the currently effective policy version.
                  </p>
                </div>
              </div>
            )}

            <div className="bk-staff-answer-text">{text}</div>

            {/* Detailed Citations with Version & Effective Date */}
            {citations.length > 0 && (
              <section className="bk-staff-citations-container">
                <h3 className="bk-citations-heading">Grounding Source Citations</h3>
                <div className="bk-detailed-citations-list">
                  {citations.map((cite, idx) => (
                    <div key={idx} className="bk-detailed-citation-item">
                      <div className="bk-cite-header">
                        <strong className="bk-cite-title">{cite.doc_title}</strong>
                        {cite.doc_id && (
                          <span className="bk-cite-id tabular-nums">{cite.doc_id}</span>
                        )}
                      </div>
                      <div className="bk-cite-details tabular-nums">
                        <span className="bk-cite-section">{cite.section}</span>
                        {cite.version && (
                          <span className="bk-cite-meta-pill">Ver: {cite.version}</span>
                        )}
                        {cite.effective_date && (
                          <span className="bk-cite-meta-pill">
                            Effective: {cite.effective_date}
                          </span>
                        )}
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
          <div className="bk-staff-card-header clarify">
            <div className="bk-status-indicator">
              <span className="bk-status-pill clarify">Clarification Follow-Up</span>
              <span className="bk-status-caption">Additional criteria needed to locate policy</span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-staff-card-body">
            <div className="bk-clarify-callout staff">
              <p className="bk-clarify-prompt">{text}</p>
              <p className="bk-clarify-hint">
                Provide clarifying criteria (e.g. customer category, transaction threshold, or
                specific policy section).
              </p>
            </div>
          </div>
        </>
      )}

      {/* 3. STATUS: DENIED */}
      {status === "denied" && (
        <>
          <div className="bk-staff-card-header denied">
            <div className="bk-status-indicator">
              <span className="bk-status-pill denied">Access Boundary Denied</span>
              <span className="bk-status-caption">Restricted compliance credentials required</span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-staff-card-body">
            <div className="bk-denied-callout staff">
              <p className="bk-denied-reason">{text}</p>
              <p className="bk-denied-hint">
                This document requires higher privilege tier than your active session ({role}).
                Access attempts are logged for compliance monitoring.
              </p>
            </div>
          </div>
        </>
      )}

      {/* 4. STATUS: ESCALATED */}
      {status === "escalated" && (
        <>
          <div className="bk-staff-card-header escalated">
            <div className="bk-status-indicator">
              <span className="bk-status-pill escalated">Escalated to Human Review</span>
              <span className="bk-status-caption">Forwarded to compliance officer review</span>
            </div>
            <time className="bk-msg-time">{timestamp}</time>
          </div>

          <div className="bk-staff-card-body">
            <div className="bk-escalated-callout staff">
              <p className="bk-escalated-reason">{text}</p>
              <div className="bk-escalated-notes">
                <p>
                  <strong>Routing:</strong> This inquiry has been logged and assigned to the senior
                  compliance officer review queue. Inquiries with low retrieval confidence or
                  factual verification failure are never answered with ungrounded speculation.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </article>
  );
}