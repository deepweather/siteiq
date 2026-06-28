/**
 * App — top-level router.
 *
 * Public:    /, /login, /signup, /forgot-password, /reset-password,
 *            /verify-email, /accept-invite, /magic-link
 * Private:   /app/*  — nested under <AppLayout/>, which mounts the
 *            shared LiveProvider + Cmd+K palette + global shortcuts.
 *            Inside it, most routes additionally render under <Chrome/>
 *            (MenuBar + Sidebar + StatusBar). The editor opts out of
 *            Chrome because its own three-panel layout needs the whole
 *            viewport.
 */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Suspense, lazy, type ReactNode } from 'react';
import { AuthProvider } from './lib/auth/AuthProvider';
import { RequireAuth } from './lib/auth/RequireAuth';
import { ErrorBoundary } from './lib/ErrorBoundary';

const LandingPage = lazy(() => import('./pages/LandingPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage'));
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'));
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage'));
const AcceptInvitePage = lazy(() => import('./pages/AcceptInvitePage'));
const MagicLinkPage = lazy(() => import('./pages/MagicLinkPage'));

const AppLayout = lazy(() => import('./shell/AppLayout'));
const Chrome = lazy(() => import('./shell/Chrome'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Portfolio = lazy(() => import('./components/Portfolio/Portfolio').then((m) => ({ default: m.Portfolio })));
const ProjectListPage = lazy(() => import('./pages/projects/ProjectListPage'));
const ProjectEditorPage = lazy(() => import('./pages/projects/ProjectEditorPage'));
const RecordPage = lazy(() => import('./pages/record/RecordPage'));
const SettingsLayout = lazy(() => import('./pages/settings/SettingsLayout'));
const AccountSettings = lazy(() => import('./pages/settings/AccountSettings'));
const TeamSettings = lazy(() => import('./pages/settings/TeamSettings'));
const OrgSwitcher = lazy(() => import('./pages/settings/OrgSwitcher'));
const Sessions = lazy(() => import('./pages/settings/Sessions'));
const Devices = lazy(() => import('./pages/settings/Devices'));

function Splash() {
  return (
    <div className="h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center mx-auto mb-4">
          <span className="text-primary-foreground text-lg font-bold">S</span>
        </div>
        <div className="text-foreground font-semibold text-sm">SiteIQ</div>
        <div className="text-muted-foreground text-xs mt-1">Loading…</div>
      </div>
    </div>
  );
}

function Lazy({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Splash />}>{children}</Suspense>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Lazy><LandingPage /></Lazy>} />
            <Route path="/login" element={<Lazy><LoginPage /></Lazy>} />
            <Route path="/signup" element={<Lazy><SignupPage /></Lazy>} />
            <Route path="/forgot-password" element={<Lazy><ForgotPasswordPage /></Lazy>} />
            <Route path="/reset-password" element={<Lazy><ResetPasswordPage /></Lazy>} />
            <Route path="/verify-email" element={<Lazy><VerifyEmailPage /></Lazy>} />
            <Route path="/accept-invite" element={<Lazy><AcceptInvitePage /></Lazy>} />
            <Route path="/magic-link" element={<Lazy><MagicLinkPage /></Lazy>} />

            <Route
              path="/app"
              element={
                <RequireAuth>
                  <Lazy><AppLayout /></Lazy>
                </RequireAuth>
              }
            >
              {/* Editor lives outside Chrome — needs the whole viewport. */}
              <Route path="projects/:id/edit" element={<Lazy><ProjectEditorPage /></Lazy>} />
              {/* Everything else renders under Chrome (menu bar, sidebar, status bar). */}
              <Route element={<Lazy><Chrome /></Lazy>}>
                <Route index element={<Lazy><Dashboard /></Lazy>} />
                <Route path="portfolio" element={<Lazy><Portfolio /></Lazy>} />
                <Route path="record" element={<Lazy><RecordPage /></Lazy>} />
                <Route path="projects" element={<Lazy><ProjectListPage /></Lazy>} />
                <Route path="settings" element={<Lazy><SettingsLayout /></Lazy>}>
                  <Route index element={<Navigate to="account" replace />} />
                  <Route path="account" element={<Lazy><AccountSettings /></Lazy>} />
                  <Route path="team" element={<Lazy><TeamSettings /></Lazy>} />
                  <Route path="devices" element={<Lazy><Devices /></Lazy>} />
                  <Route path="orgs" element={<Lazy><OrgSwitcher /></Lazy>} />
                  <Route path="sessions" element={<Lazy><Sessions /></Lazy>} />
                </Route>
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
