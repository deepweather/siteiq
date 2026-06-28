/** Worker PWA entry. Same-origin under /worker/, so it reuses the shared
 *  AuthProvider (cookie + CSRF) verbatim. */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '../lib/auth/AuthProvider';
import { ErrorBoundary } from '../lib/ErrorBoundary';
import { I18nProvider } from './I18nProvider';
import { registerWorkerSW } from './pwa';
import WorkerApp from './WorkerApp';
import '../index.css';

registerWorkerSW();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter basename="/worker">
        <I18nProvider>
          <AuthProvider>
            <WorkerApp />
          </AuthProvider>
        </I18nProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);
