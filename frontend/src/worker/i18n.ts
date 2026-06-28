/**
 * Tiny i18n core for the worker PWA. German-first (DACH crews) with an
 * English fallback toggle. Deliberately a plain dictionary + context — no
 * heavy library on a phone used in a dead zone.
 *
 * The provider component lives in `I18nProvider.tsx`; the context, hook,
 * and dictionaries live here so the `.tsx` only exports a component
 * (keeps React Fast Refresh happy — mirrors `shell/LiveContext`).
 */
import { createContext, useCallback, useContext, useMemo, useState } from 'react';

export type Lang = 'de' | 'en';

export const LANG_STORAGE_KEY = 'siteiq.worker.lang';

type Dict = Record<string, string>;

const DE: Dict = {
  appName: 'SiteIQ Crew',
  'tab.home': 'Start',
  'tab.assets': 'Material',
  'tab.entries': 'Einträge',
  greeting: 'Hallo',
  'action.delivery': 'Lieferung',
  'action.incident': 'Problem',
  'action.inspection': 'Prüfung',
  'action.note': 'Notiz',
  'status.online': 'Online',
  'status.offline': 'Offline',
  'status.syncing': 'Synchronisiere…',
  'status.pending': '{n} wartet',
  'login.title': 'Anmelden',
  'login.lead': 'Gib deine E-Mail ein. Wir schicken dir einen Link zum Anmelden.',
  'login.email': 'E-Mail',
  'login.send': 'Link senden',
  'login.sent.title': 'E-Mail unterwegs',
  'login.sent.sub': 'Öffne den Link auf diesem Gerät, um dich anzumelden.',
  'login.signingIn': 'Anmeldung läuft…',
  'login.failed': 'Anmeldung fehlgeschlagen. Bitte fordere einen neuen Link an.',
  'entry.review': 'Prüfen',
  'entry.send': 'Senden',
  'entry.back': 'Zurück',
  'entry.next': 'Weiter',
  'delivery.what': 'Was wurde geliefert?',
  'delivery.howMuch': 'Wie viel?',
  'delivery.where': 'Wohin?',
  'material.rebar': 'Bewehrung',
  'material.concrete': 'Beton',
  'material.conduit': 'Leerrohr',
  'material.drywall': 'Trockenbau',
  'material.aggregate': 'Schotter',
  'material.other': 'Andere',
  'incident.severity': 'Wie ernst ist es?',
  'severity.low': 'Gering',
  'severity.med': 'Mittel',
  'severity.high': 'Hoch',
  'incident.where': 'Wo?',
  'incident.describe': 'Kurz beschreiben',
  'inspection.result': 'Ergebnis?',
  'inspection.pass': 'Bestanden',
  'inspection.fail': 'Durchgefallen',
  'inspection.where': 'Welcher Bereich?',
  'note.title': 'Notiz',
  'note.placeholder': 'Was möchtest du festhalten?',
  'where.none': 'Kein Bereich',
  'result.sent.title': 'Gesendet',
  'result.sent.sub': 'Wartet auf Freigabe durch den Polier.',
  'result.queued.title': 'Gespeichert',
  'result.queued.sub': 'Wird gesendet, sobald du wieder online bist.',
  'result.done': 'Fertig',
  'assets.search': 'Suchen…',
  'assets.all': 'Alle',
  'assets.material': 'Material',
  'assets.equipment': 'Geräte',
  'assets.zone': 'Bereiche',
  'asset.onHand': 'vorhanden',
  'asset.utilization': 'Auslastung',
  'asset.events': 'Letzte Ereignisse',
  'asset.empty': 'Keine Daten gefunden.',
  'entries.title': 'Meine Einträge',
  'entries.empty': 'Noch keine Einträge.',
  'entries.status.proposed': 'Wartet auf Freigabe',
  'entries.status.confirmed': 'Bestätigt',
  'entries.status.rejected': 'Abgelehnt',
  'entries.pendingSync': 'Wird gesendet…',
  'common.voice': 'Diktieren',
  'common.optional': 'optional',
  'common.loading': 'Lädt…',
  'common.retry': 'Erneut versuchen',
  'common.signout': 'Abmelden',
  'common.qty': 'Menge',
};

const EN: Dict = {
  appName: 'SiteIQ Crew',
  'tab.home': 'Home',
  'tab.assets': 'Assets',
  'tab.entries': 'Entries',
  greeting: 'Hi',
  'action.delivery': 'Delivery',
  'action.incident': 'Issue',
  'action.inspection': 'Inspection',
  'action.note': 'Note',
  'status.online': 'Online',
  'status.offline': 'Offline',
  'status.syncing': 'Syncing…',
  'status.pending': '{n} queued',
  'login.title': 'Sign in',
  'login.lead': 'Enter your email. We send you a link to sign in.',
  'login.email': 'Email',
  'login.send': 'Send link',
  'login.sent.title': 'Check your email',
  'login.sent.sub': 'Open the link on this device to sign in.',
  'login.signingIn': 'Signing in…',
  'login.failed': 'Sign-in failed. Please request a new link.',
  'entry.review': 'Review',
  'entry.send': 'Send',
  'entry.back': 'Back',
  'entry.next': 'Next',
  'delivery.what': 'What was delivered?',
  'delivery.howMuch': 'How much?',
  'delivery.where': 'Where to?',
  'material.rebar': 'Rebar',
  'material.concrete': 'Concrete',
  'material.conduit': 'Conduit',
  'material.drywall': 'Drywall',
  'material.aggregate': 'Aggregate',
  'material.other': 'Other',
  'incident.severity': 'How serious is it?',
  'severity.low': 'Low',
  'severity.med': 'Medium',
  'severity.high': 'High',
  'incident.where': 'Where?',
  'incident.describe': 'Describe briefly',
  'inspection.result': 'Result?',
  'inspection.pass': 'Pass',
  'inspection.fail': 'Fail',
  'inspection.where': 'Which area?',
  'note.title': 'Note',
  'note.placeholder': 'What do you want to record?',
  'where.none': 'No area',
  'result.sent.title': 'Sent',
  'result.sent.sub': 'Waiting for supervisor approval.',
  'result.queued.title': 'Saved',
  'result.queued.sub': 'Will send once you are back online.',
  'result.done': 'Done',
  'assets.search': 'Search…',
  'assets.all': 'All',
  'assets.material': 'Material',
  'assets.equipment': 'Equipment',
  'assets.zone': 'Areas',
  'asset.onHand': 'on hand',
  'asset.utilization': 'Utilization',
  'asset.events': 'Recent activity',
  'asset.empty': 'No data found.',
  'entries.title': 'My entries',
  'entries.empty': 'No entries yet.',
  'entries.status.proposed': 'Awaiting review',
  'entries.status.confirmed': 'Confirmed',
  'entries.status.rejected': 'Rejected',
  'entries.pendingSync': 'Sending…',
  'common.voice': 'Dictate',
  'common.optional': 'optional',
  'common.loading': 'Loading…',
  'common.retry': 'Try again',
  'common.signout': 'Sign out',
  'common.qty': 'Quantity',
};

const DICTS: Record<Lang, Dict> = { de: DE, en: EN };

export type Translate = (key: string, params?: Record<string, string | number>) => string;

export interface I18nShape {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: Translate;
}

export const I18nContext = createContext<I18nShape | null>(null);

function initialLang(): Lang {
  const stored = (typeof localStorage !== 'undefined' && localStorage.getItem(LANG_STORAGE_KEY)) as Lang | null;
  if (stored === 'de' || stored === 'en') return stored;
  if (typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('en')) return 'en';
  return 'de';
}

/** Builds the i18n context value. Lives here (not in the provider .tsx) so
 *  the provider file exports only a component. */
export function useI18nValue(): I18nShape {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(LANG_STORAGE_KEY, l);
    } catch {
      /* private mode — ignore */
    }
  }, []);

  const t = useCallback<Translate>(
    (key, params) => {
      let s = DICTS[lang][key] ?? DICTS.en[key] ?? key;
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          s = s.replace(`{${k}}`, String(v));
        }
      }
      return s;
    },
    [lang],
  );

  return useMemo<I18nShape>(() => ({ lang, setLang, t }), [lang, setLang, t]);
}

export function useI18n(): I18nShape {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>');
  return ctx;
}
