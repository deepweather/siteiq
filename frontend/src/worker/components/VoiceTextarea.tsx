/**
 * Textarea with optional voice dictation. Workers in gloves would rather
 * talk than type, so when the browser supports SpeechRecognition we show a
 * big mic button that appends transcribed text. Progressive enhancement —
 * the plain textarea always works.
 */
import { useRef, useState } from 'react';
import { useI18n } from '../i18n';

// Minimal structural types for the (prefixed) Web Speech API.
interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

function getRecognition(lang: string): SpeechRecognitionLike | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = lang;
  rec.interimResults = false;
  rec.continuous = false;
  return rec;
}

export function VoiceTextarea({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (s: string) => void;
  placeholder?: string;
}) {
  const { t, lang } = useI18n();
  const [listening, setListening] = useState(false);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const supported = typeof window !== 'undefined' && getRecognition('en') !== null;

  const toggle = () => {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const rec = getRecognition(lang === 'de' ? 'de-DE' : 'en-US');
    if (!rec) return;
    recRef.current = rec;
    rec.onresult = (e: SpeechResultEvent) => {
      const text = Array.from(e.results)
        .map((r) => r[0].transcript)
        .join(' ');
      onChange(value ? `${value} ${text}` : text);
    };
    rec.onend = () => setListening(false);
    setListening(true);
    rec.start();
  };

  return (
    <div className="space-y-3">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={4}
        className="w-full rounded-2xl border-2 border-border bg-card p-4 text-lg
          text-foreground outline-none focus:border-primary resize-none"
      />
      {supported ? (
        <button
          onClick={toggle}
          className={`w-full min-h-[60px] rounded-2xl text-lg font-semibold border-2
            active:scale-[0.98] transition-transform
            ${listening ? 'border-destructive bg-destructive/10 text-destructive' : 'border-border bg-card text-foreground'}`}
        >
          {listening ? '● …' : `🎤 ${t('common.voice')}`}
        </button>
      ) : null}
    </div>
  );
}
