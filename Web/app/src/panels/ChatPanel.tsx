export type ChatKind = "create" | "understand";

const COPY: Record<ChatKind, { empty: string; placeholder: string; model: string }> = {
  create: {
    empty: "Discuss an idea, pick references, generate images and refine the results here.",
    placeholder: "Describe the image you want to create…",
    model: "Conversation + image model",
  },
  understand: {
    empty: "Analyze screenshots, extract text, search knowledge and organize the library here.",
    placeholder: "Ask about a screenshot, a reference or your library…",
    model: "Vision + tools model",
  },
};

/** Static shell. Streaming, tools and model selection arrive with the connected-agents milestone. */
export function ChatPanel({ kind }: { kind: ChatKind }) {
  const copy = COPY[kind];
  return (
    <div className="chat">
      <label className="field">
        <span className="muted">{copy.model}</span>
        <select disabled aria-label={`${kind} model`}>
          <option>Not connected</option>
        </select>
      </label>
      <div className="chat-log" role="log" aria-live="polite">
        <p className="muted">{copy.empty}</p>
      </div>
      <form className="chat-composer" onSubmit={(e) => e.preventDefault()}>
        <textarea disabled rows={3} placeholder={copy.placeholder} aria-label={`${kind} message`} />
        <button type="submit" disabled>
          Send
        </button>
      </form>
      <p className="muted">Agents connect in a later milestone.</p>
    </div>
  );
}
