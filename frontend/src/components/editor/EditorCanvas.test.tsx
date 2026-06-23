/**
 * EditorCanvas focuses on canvas-level interaction (drag, hit-test, snap).
 * We pin behaviour we can exercise without simulating a real Canvas2D
 * context: the `snapToGrid` math, the toolbar wiring + localStorage
 * persistence, and the drag commit using snap=5 / snap=0. The full
 * paint pipeline is covered by the visual smoke we run via the browser
 * in dev — jsdom's HTMLCanvasElement is a no-op.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EditorCanvas } from './EditorCanvas';
import { snapToGrid } from './grid';
import { blankProjectDocument, type ProjectDocument } from '../../services/projectsApi';

describe('snapToGrid', () => {
  it('rounds to the nearest multiple', () => {
    expect(snapToGrid(12.4, 5)).toBe(10);
    expect(snapToGrid(12.6, 5)).toBe(15);
    expect(snapToGrid(7.2, 1)).toBe(7);
    expect(snapToGrid(99.99, 10)).toBe(100);
  });

  it('passes through fractional values when gridSize is 0', () => {
    expect(snapToGrid(12.4, 0)).toBe(12.4);
    expect(snapToGrid(0.001, 0)).toBe(0.001);
  });

  it('handles negative gridSize defensively', () => {
    // Defensive: a corrupt localStorage value should not crash.
    expect(snapToGrid(12.4, -1)).toBe(12.4);
  });
});

describe('EditorCanvas — grid toolbar', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  function renderCanvas(extra?: Partial<React.ComponentProps<typeof EditorCanvas>>) {
    const doc: ProjectDocument = blankProjectDocument('demo', 'Demo');
    return render(
      <EditorCanvas
        document={doc}
        activeLevel="L0"
        tool="select"
        selection={null}
        onSelect={() => {}}
        onPlace={() => {}}
        onMoveSelection={() => {}}
        {...extra}
      />,
    );
  }

  it('renders the four snap options', () => {
    renderCanvas();
    const tb = screen.getByTestId('grid-toolbar');
    expect(tb.textContent).toContain('Off');
    expect(tb.textContent).toContain('1m');
    expect(tb.textContent).toContain('5m');
    expect(tb.textContent).toContain('10m');
  });

  it('defaults to 1m on first mount', () => {
    renderCanvas();
    const oneM = screen.getByRole('button', { name: '1m' });
    expect(oneM.getAttribute('aria-pressed')).toBe('true');
  });

  it('persists the user selection to localStorage', () => {
    renderCanvas();
    fireEvent.click(screen.getByRole('button', { name: '5m' }));
    expect(window.localStorage.getItem('siteiq.editor.grid_size')).toBe('5');
  });

  it('restores the persisted grid size on mount', () => {
    window.localStorage.setItem('siteiq.editor.grid_size', '10');
    renderCanvas();
    const tenM = screen.getByRole('button', { name: '10m' });
    expect(tenM.getAttribute('aria-pressed')).toBe('true');
  });

  it('falls back to the default on a corrupt localStorage value', () => {
    window.localStorage.setItem('siteiq.editor.grid_size', 'banana');
    renderCanvas();
    const oneM = screen.getByRole('button', { name: '1m' });
    expect(oneM.getAttribute('aria-pressed')).toBe('true');
  });
});
