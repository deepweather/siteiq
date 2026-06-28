/**
 * The core loop: one question per screen, then a review, then submit.
 * A single wizard drives all four entry kinds (delivery / incident /
 * inspection / note) off a per-kind step list. Submission always goes
 * through the offline outbox, so it works with no signal.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useI18n } from '../i18n';
import { workerApi, type EntryKind } from '../workerApi';
import { outbox, newClientEventId, type OutboxItem } from '../offlineQueue';
import {
  Screen,
  WorkerButton,
  BigChoice,
  ChipGroup,
  Stepper,
  FieldLabel,
  type Choice,
} from '../components/ui';
import { VoiceTextarea } from '../components/VoiceTextarea';
import { ResultScreen } from '../components/ResultScreen';

const KINDS: EntryKind[] = ['delivery', 'incident', 'inspection', 'note'];

const MATERIALS: { id: string; emoji: string; unit: string }[] = [
  { id: 'rebar', emoji: '🪨', unit: 't' },
  { id: 'concrete', emoji: '🪣', unit: 'm³' },
  { id: 'conduit', emoji: '🔌', unit: 'm' },
  { id: 'drywall', emoji: '🧱', unit: 'Plt' },
  { id: 'aggregate', emoji: '⛏️', unit: 't' },
  { id: 'other', emoji: '➕', unit: 'Stk' },
];

const KIND_EMOJI: Record<EntryKind, string> = {
  delivery: '📦',
  incident: '⚠️',
  inspection: '✅',
  note: '📝',
};

interface StepDef {
  title: string;
  body: ReactNode;
  canNext: boolean;
}

export default function EntryWizard() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { kind } = useParams<{ kind: string }>();
  const validKind = (KINDS as string[]).includes(kind ?? '') ? (kind as EntryKind) : null;

  const [step, setStep] = useState(0);
  const [material, setMaterial] = useState<string | null>(null);
  const [qty, setQty] = useState(1);
  const [zoneId, setZoneId] = useState<string | null>(null);
  const [severity, setSeverity] = useState<string | null>(null);
  const [result, setResult] = useState<'pass' | 'fail' | null>(null);
  const [note, setNote] = useState('');
  const [zones, setZones] = useState<Choice[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [outcome, setOutcome] = useState<'sent' | 'queued' | null>(null);
  // Stable idempotency key for the whole life of this form instance.
  const [cid] = useState(newClientEventId);

  useEffect(() => {
    if (!validKind) navigate('/', { replace: true });
  }, [validKind, navigate]);

  useEffect(() => {
    workerApi
      .zones()
      .then((r) => setZones(r.zones.map((z) => ({ id: z.id, label: z.label }))))
      .catch(() => setZones([]));
  }, []);

  const unit = MATERIALS.find((m) => m.id === material)?.unit ?? 'Stk';

  const zoneChoicesOptional: Choice[] = useMemo(
    () => [{ id: '__none__', label: t('where.none') }, ...zones],
    [zones, t],
  );

  const whereStep = (optional: boolean): StepDef => ({
    title: t(validKind === 'incident' ? 'incident.where' : validKind === 'inspection' ? 'inspection.where' : 'delivery.where'),
    body: (
      <ChipGroup
        choices={optional ? zoneChoicesOptional : zones}
        value={zoneId ?? (optional ? '__none__' : null)}
        onSelect={(id) => setZoneId(id === '__none__' ? null : id)}
      />
    ),
    canNext: optional ? true : zoneId !== null,
  });

  const reviewStep: StepDef = {
    title: t('entry.review'),
    body: <Review kind={validKind!} material={material} qty={qty} unit={unit} zoneId={zoneId} zones={zones} severity={severity} result={result} note={note} />,
    canNext: true,
  };

  const steps: StepDef[] = useMemo(() => {
    if (!validKind) return [];
    if (validKind === 'delivery') {
      return [
        {
          title: t('delivery.what'),
          body: (
            <BigChoice
              choices={MATERIALS.map((m) => ({ id: m.id, emoji: m.emoji, label: t(`material.${m.id}`) }))}
              value={material}
              onSelect={setMaterial}
            />
          ),
          canNext: material !== null,
        },
        {
          title: t('delivery.howMuch'),
          body: <Stepper value={qty} unit={unit} onChange={setQty} />,
          canNext: qty > 0,
        },
        whereStep(false),
        reviewStep,
      ];
    }
    if (validKind === 'incident') {
      return [
        {
          title: t('incident.severity'),
          body: (
            <BigChoice
              choices={[
                { id: 'low', emoji: '🟢', label: t('severity.low') },
                { id: 'med', emoji: '🟠', label: t('severity.med') },
                { id: 'high', emoji: '🔴', label: t('severity.high') },
              ]}
              value={severity}
              onSelect={setSeverity}
            />
          ),
          canNext: severity !== null,
        },
        whereStep(true),
        {
          title: `${t('incident.describe')} (${t('common.optional')})`,
          body: <VoiceTextarea value={note} onChange={setNote} placeholder={t('incident.describe')} />,
          canNext: true,
        },
        reviewStep,
      ];
    }
    if (validKind === 'inspection') {
      return [
        {
          title: t('inspection.result'),
          body: (
            <BigChoice
              choices={[
                { id: 'pass', emoji: '✅', label: t('inspection.pass') },
                { id: 'fail', emoji: '❌', label: t('inspection.fail') },
              ]}
              value={result}
              onSelect={(id) => setResult(id as 'pass' | 'fail')}
            />
          ),
          canNext: result !== null,
        },
        whereStep(false),
        reviewStep,
      ];
    }
    // note
    return [
      {
        title: t('note.title'),
        body: <VoiceTextarea value={note} onChange={setNote} placeholder={t('note.placeholder')} />,
        canNext: note.trim() !== '',
      },
      whereStep(true),
      reviewStep,
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [validKind, material, qty, unit, zoneId, severity, result, note, zones, t]);

  if (!validKind || steps.length === 0) return null;
  if (outcome) {
    return <ResultScreen outcome={outcome} onDone={() => navigate('/', { replace: true })} />;
  }

  const current = steps[step];
  const isLast = step === steps.length - 1;

  const buildPayload = (): Record<string, unknown> => {
    switch (validKind) {
      case 'delivery':
        return { subtype: material, quantity: qty, unit, zone_id: zoneId };
      case 'incident':
        return { severity, zone_id: zoneId, note: note || undefined };
      case 'inspection':
        return { result, zone_id: zoneId, note: note || undefined };
      default:
        return { note, zone_id: zoneId || undefined };
    }
  };

  const submit = async () => {
    setSubmitting(true);
    const item: OutboxItem = {
      kind: validKind,
      client_event_id: cid,
      payload: buildPayload(),
      occurred_at: new Date().toISOString(),
      created_at: Date.now(),
    };
    try {
      const res = await outbox.submitOrQueue(item);
      setOutcome(res);
    } catch {
      // 4xx — shouldn't happen with controlled inputs; treat as queued-failed.
      setSubmitting(false);
    }
  };

  const back = () => (step === 0 ? navigate(-1) : setStep((s) => s - 1));

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex items-center gap-3 px-4 pt-3">
        <button onClick={back} className="w-12 h-12 rounded-full bg-secondary text-2xl active:scale-95" aria-label={t('entry.back')}>
          ‹
        </button>
        <div className="flex items-center gap-2 font-semibold text-lg text-foreground">
          <span aria-hidden>{KIND_EMOJI[validKind]}</span>
          {t(`action.${validKind}`)}
        </div>
        <div className="ml-auto flex gap-1">
          {steps.map((_, i) => (
            <span key={i} className={`w-2 h-2 rounded-full ${i <= step ? 'bg-primary' : 'bg-border'}`} />
          ))}
        </div>
      </div>

      <Screen className="flex-1">
        <FieldLabel>{current.title}</FieldLabel>
        {current.body}
      </Screen>

      <div className="px-4 pb-6 pt-2">
        {isLast ? (
          <WorkerButton variant="success" onClick={submit} disabled={submitting}>
            {t('entry.send')}
          </WorkerButton>
        ) : (
          <WorkerButton onClick={() => setStep((s) => s + 1)} disabled={!current.canNext}>
            {t('entry.next')}
          </WorkerButton>
        )}
      </div>
    </div>
  );
}

function Review(props: {
  kind: EntryKind;
  material: string | null;
  qty: number;
  unit: string;
  zoneId: string | null;
  zones: Choice[];
  severity: string | null;
  result: 'pass' | 'fail' | null;
  note: string;
}) {
  const { t } = useI18n();
  const zoneLabel = props.zoneId
    ? props.zones.find((z) => z.id === props.zoneId)?.label ?? props.zoneId
    : t('where.none');

  const rows: [string, string][] = [];
  if (props.kind === 'delivery') {
    rows.push([t('action.delivery'), `${t(`material.${props.material}`)} · ${props.qty} ${props.unit}`]);
    rows.push([t('delivery.where'), zoneLabel]);
  } else if (props.kind === 'incident') {
    rows.push([t('incident.severity'), t(`severity.${props.severity}`)]);
    rows.push([t('incident.where'), zoneLabel]);
    if (props.note) rows.push([t('incident.describe'), props.note]);
  } else if (props.kind === 'inspection') {
    rows.push([t('inspection.result'), t(`inspection.${props.result}`)]);
    rows.push([t('inspection.where'), zoneLabel]);
  } else {
    rows.push([t('note.title'), props.note]);
    rows.push([t('incident.where'), zoneLabel]);
  }

  return (
    <div className="rounded-2xl border-2 border-border bg-card divide-y divide-border">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4 px-4 py-4">
          <span className="text-muted-foreground">{k}</span>
          <span className="font-semibold text-foreground text-right">{v}</span>
        </div>
      ))}
    </div>
  );
}
