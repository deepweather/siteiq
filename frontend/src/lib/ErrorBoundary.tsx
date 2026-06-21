/**
 * Top-level React error boundary.
 *
 * Catches anything an inner component throws during render or in a
 * lifecycle phase, logs it (so prod observability picks it up), and
 * shows a clean recovery card instead of a blank page or a partial
 * tree. The "Reload" button forces a full reload — the most reliable
 * way to recover from a corrupted state tree without inventing custom
 * reset hooks per feature.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Wire up Sentry / Datadog here when we have one. For now, browser
    // console is enough to surface in dev and to be picked up by any
    // standard error-tracking script tag.
    // eslint-disable-next-line no-console
    console.error('Unhandled UI error:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="h-screen flex items-center justify-center bg-background p-6">
          <div className="max-w-md w-full text-center">
            <div className="w-12 h-12 bg-destructive/10 text-destructive rounded-lg flex items-center justify-center mx-auto mb-4 text-2xl font-semibold">
              !
            </div>
            <h1 className="text-2xl font-semibold tracking-tight mb-2">
              Something went sideways.
            </h1>
            <p className="text-sm text-muted-foreground mb-6">
              The app hit an error it couldn't recover from. Reloading
              usually fixes it. If it keeps happening, copy the error
              below and let us know.
            </p>
            <pre className="text-xs text-left bg-muted text-muted-foreground p-3 rounded-md mb-6 overflow-auto max-h-40">
              {String(this.state.error.stack ?? this.state.error.message)}
            </pre>
            <button
              onClick={() => window.location.reload()}
              className="rounded-md bg-primary text-primary-foreground font-semibold text-sm px-5 py-2.5 hover:bg-primary/90"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
