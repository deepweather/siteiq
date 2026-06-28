/**
 * Worker PWA router + chrome.
 *
 * A persistent bottom tab bar (Home / Assets / Entries) per the chosen
 * navigation model, a top status strip (connectivity + pending sync +
 * language), and the entry wizard which opens full-screen over the tabs.
 */
import { useEffect } from 'react';
import {
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { auth } from '../services/api';
import { useI18n } from './i18n';
import { useOnline, useOutbox } from './hooks';
import { outbox } from './offlineQueue';
import { RequireWorkerAuth } from './RequireWorkerAuth';
import WorkerLogin from './pages/WorkerLogin';
import WorkerHome from './pages/WorkerHome';
import EntryWizard from './pages/EntryWizard';
import AssetList from './pages/AssetList';
import AssetDetail from './pages/AssetDetail';
import MyEntries from './pages/MyEntries';

function StatusStrip() {
  const { t, lang, setLang } = useI18n();
  const online = useOnline();
  const { pending, flushing } = useOutbox();

  // Drain the outbox whenever we (re)gain connectivity or mount online.
  useEffect(() => {
    if (online) void outbox.flush();
  }, [online]);

  let center: string;
  let tint: string;
  if (!online) {
    center = pending > 0 ? `${t('status.offline')} · ${t('status.pending', { n: pending })}` : t('status.offline');
    tint = 'text-warning';
  } else if (flushing || pending > 0) {
    center = flushing ? t('status.syncing') : t('status.pending', { n: pending });
    tint = 'text-warning';
  } else {
    center = t('status.online');
    tint = 'text-success';
  }

  return (
    <header className="sticky top-0 z-30 bg-card border-b border-border">
      <div className="flex items-center gap-2 px-3 h-12">
        <span className={`flex items-center gap-1.5 text-sm font-medium ${tint}`}>
          <span className={`w-2.5 h-2.5 rounded-full ${online && pending === 0 && !flushing ? 'bg-success' : 'bg-warning'}`} />
          {center}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => setLang(lang === 'de' ? 'en' : 'de')}
            className="px-3 h-9 rounded-full bg-secondary text-sm font-semibold uppercase"
          >
            {lang}
          </button>
          <button
            onClick={() => auth.logout()}
            className="px-3 h-9 rounded-full bg-secondary text-sm"
            aria-label="sign out"
          >
            ⏻
          </button>
        </div>
      </div>
    </header>
  );
}

function TabBar() {
  const { t } = useI18n();
  const tabs = [
    { to: '/', emoji: '🏠', label: t('tab.home'), end: true },
    { to: '/assets', emoji: '🔍', label: t('tab.assets'), end: false },
    { to: '/entries', emoji: '🕓', label: t('tab.entries'), end: false },
  ];
  return (
    <nav className="sticky bottom-0 z-30 bg-card border-t border-border grid grid-cols-3 pb-[env(safe-area-inset-bottom)]">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            `flex flex-col items-center justify-center gap-0.5 py-2.5 min-h-[60px] ${
              isActive ? 'text-primary' : 'text-muted-foreground'
            }`
          }
        >
          <span className="text-2xl" aria-hidden>{tab.emoji}</span>
          <span className="text-xs font-medium">{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

/** Authenticated shell: status strip on top, tab bar at the bottom, the
 *  active page in between. The entry wizard hides the tab bar (it's a
 *  full-screen task), so it renders outside this layout. */
function Shell() {
  const location = useLocation();
  const hideTabs = location.pathname.startsWith('/new/');
  return (
    <div className="min-h-screen flex flex-col bg-background">
      <StatusStrip />
      <main className="flex-1 overflow-y-auto flex flex-col">
        <Outlet />
      </main>
      {!hideTabs ? <TabBar /> : null}
    </div>
  );
}

export default function WorkerApp() {
  // Re-check auth on focus is handled by AuthProvider's boot; here we just
  // try to flush the outbox once on mount in case we came back online cold.
  useEffect(() => {
    void outbox.flush();
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<WorkerLogin />} />
      <Route
        element={
          <RequireWorkerAuth>
            <Shell />
          </RequireWorkerAuth>
        }
      >
        <Route index element={<WorkerHome />} />
        <Route path="new/:kind" element={<EntryWizard />} />
        <Route path="assets" element={<AssetList />} />
        <Route path="assets/:type/:id" element={<AssetDetail />} />
        <Route path="entries" element={<MyEntries />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
