/** Full-screen confirmation after an entry. Honest about state: "Sent —
 *  waiting for approval" online (entries are `proposed`), or "Saved — will
 *  send when online" when it went to the outbox. */
import { useI18n } from '../i18n';
import { WorkerButton } from './ui';

export function ResultScreen({
  outcome,
  onDone,
}: {
  outcome: 'sent' | 'queued';
  onDone: () => void;
}) {
  const { t } = useI18n();
  const sent = outcome === 'sent';
  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col items-center justify-center px-8 text-center">
      <div
        className={`w-28 h-28 rounded-full flex items-center justify-center text-6xl mb-6
          ${sent ? 'bg-success/15 text-success' : 'bg-warning/15 text-warning'}`}
        aria-hidden
      >
        {sent ? '✓' : '⏳'}
      </div>
      <h1 className="text-3xl font-bold text-foreground mb-2">
        {sent ? t('result.sent.title') : t('result.queued.title')}
      </h1>
      <p className="text-lg text-muted-foreground mb-10 max-w-xs">
        {sent ? t('result.sent.sub') : t('result.queued.sub')}
      </p>
      <div className="w-full max-w-sm">
        <WorkerButton variant={sent ? 'success' : 'primary'} onClick={onDone}>
          {t('result.done')}
        </WorkerButton>
      </div>
    </div>
  );
}
