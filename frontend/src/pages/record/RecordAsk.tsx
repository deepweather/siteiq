import { useState } from 'react';
import { recordApi, type QueryAnswer } from '../../services/recordApi';

const SUGGESTIONS = [
  'How many idle equipment hours and what did they cost?',
  'How many deliveries were recorded?',
  'How many worker hours were logged?',
  'What is the total recorded cost?',
];

/** Conversational query over the ledger. Deterministic backend today;
 *  the same endpoint upgrades to an LLM responder behind the seam later. */
export default function RecordAsk() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<QueryAnswer | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setQuestion(text);
    setLoading(true);
    try {
      setAnswer(await recordApi.query(text));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about idle equipment, deliveries, labour, or cost…"
          className="flex-1 rounded-md border border-border bg-card px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? 'Asking…' : 'Ask'}
        </button>
      </form>

      <div className="flex flex-wrap gap-2 mt-3">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => ask(s)}
            className="text-xs rounded-full border border-border px-3 py-1 text-muted-foreground hover:bg-secondary"
          >
            {s}
          </button>
        ))}
      </div>

      {answer && (
        <div className="mt-6 rounded-xl border border-border bg-card p-5" data-testid="ask-answer">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
            {answer.intent}
          </div>
          <div className="text-lg">{answer.answer}</div>
          {answer.supporting_event_ids.length > 0 && (
            <div className="text-xs text-muted-foreground mt-3 font-mono">
              Backed by {answer.supporting_event_ids.length} event
              {answer.supporting_event_ids.length === 1 ? '' : 's'}.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
