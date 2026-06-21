/**
 * App — top-level router.
 *
 * Public:    /, /login, /signup, /forgot-password, /reset-password,
 *            /verify-email, /accept-invite
 * Private:   /app/* (gated by RequireAuth)
 */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './lib/auth/AuthProvider';
import { RequireAuth } from './lib/auth/RequireAuth';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import AcceptInvitePage from './pages/AcceptInvitePage';
import Dashboard from './pages/Dashboard';
import SettingsLayout from './pages/settings/SettingsLayout';
import AccountSettings from './pages/settings/AccountSettings';
import TeamSettings from './pages/settings/TeamSettings';
import OrgSwitcher from './pages/settings/OrgSwitcher';
import Sessions from './pages/settings/Sessions';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/accept-invite" element={<AcceptInvitePage />} />

          <Route
            path="/app"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />

          <Route
            path="/app/settings"
            element={
              <RequireAuth>
                <SettingsLayout />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="account" replace />} />
            <Route path="account" element={<AccountSettings />} />
            <Route path="team" element={<TeamSettings />} />
            <Route path="orgs" element={<OrgSwitcher />} />
            <Route path="sessions" element={<Sessions />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
