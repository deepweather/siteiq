/**
 * Bug #4 — Recommendations celebration card must reset on project switch
 * (i.e. when the recommendation signature changes).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { Recommendations } from './Recommendations';
import type { Recommendation } from '../../types/analytics';

async function flushAsync() {
  // Yield to the microtask queue so React commits queued state updates.
  await act(async () => { await Promise.resolve(); });
}

const makeRec = (id: string, applied = false): Recommendation => ({
  id,
  type: 'move_facility',
  title: id,
  description: 'd',
  target_asset_id: id,
  from_position: { x: 0, y: 0 },
  to_position: { x: 10, y: 10 },
  daily_savings: 100,
  monthly_savings: 2200,
  applied,
});

describe('Recommendations celebration card (bug #4)', () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    // Reset cached CSRF token from prior tests so /auth/csrf is re-fetched.
    const { clearCsrfCache } = await import('../../services/api');
    clearCsrfCache();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) {
        return new Response(JSON.stringify({ csrf_token: 'rec-test-csrf' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('null', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
  });

  it('does NOT show celebration card initially', () => {
    const recs = [makeRec('a'), makeRec('b')];
    render(<Recommendations recommendations={recs} onRecsChange={() => {}} />);
    expect(screen.queryByText(/all optimizations applied/i)).toBeNull();
  });

  // Button text is broken across spans now ("Apply all — save €X/mo"), so
  // we identify it by role + accessible name regex match.
  const clickApplyAll = () => {
    const btn = screen.getByRole('button', { name: /apply all.*save/i });
    fireEvent.click(btn);
  };

  it('shows celebration card after clicking Apply All', async () => {
    const recs = [makeRec('a'), makeRec('b')];
    let nextRecs = recs;
    const onChange = (r: Recommendation[]) => { nextRecs = r; };
    const { rerender } = render(<Recommendations recommendations={recs} onRecsChange={onChange} />);

    await act(async () => {
      clickApplyAll();
    });
    await flushAsync();
    expect(nextRecs.every(r => r.applied)).toBe(true);

    rerender(<Recommendations recommendations={nextRecs} onRecsChange={onChange} />);
    expect(await screen.findByText(/All Optimizations Applied/i)).toBeInTheDocument();
  });

  it('HIDES celebration card when recommendation set changes (project switch)', async () => {
    const recs = [makeRec('a'), makeRec('b')];
    let nextRecs = recs;
    const onChange = (r: Recommendation[]) => { nextRecs = r; };
    const { rerender } = render(<Recommendations recommendations={recs} onRecsChange={onChange} />);

    await act(async () => {
      clickApplyAll();
    });
    await flushAsync();
    rerender(<Recommendations recommendations={nextRecs} onRecsChange={onChange} />);
    expect(await screen.findByText(/All Optimizations Applied/i)).toBeInTheDocument();

    // Simulate a project switch — different recommendation ids arrive
    const projectSwitchRecs = [makeRec('x'), makeRec('y'), makeRec('z')];
    rerender(<Recommendations recommendations={projectSwitchRecs} onRecsChange={onChange} />);

    // Celebration card MUST be gone now
    expect(screen.queryByText(/All Optimizations Applied/i)).toBeNull();
    expect(screen.getByRole('button', { name: /apply all.*save/i })).toBeInTheDocument();
  });

  it('shows celebration when same recommendation signature returns from backend post-apply', async () => {
    // Common case: applyAll posts, then the 5s poll returns the SAME recs
    // marked applied=true on the backend. Signature is unchanged.
    const recs = [makeRec('a'), makeRec('b')];
    let nextRecs = recs;
    const { rerender } = render(<Recommendations recommendations={recs} onRecsChange={(r) => { nextRecs = r; }} />);

    await act(async () => {
      clickApplyAll();
    });
    await flushAsync();
    rerender(<Recommendations recommendations={nextRecs} onRecsChange={() => {}} />);
    expect(await screen.findByText(/All Optimizations Applied/i)).toBeInTheDocument();

    // The 5s poll returns the same rec ids (server-side state)
    const polled = [makeRec('a', true), makeRec('b', true)];
    rerender(<Recommendations recommendations={polled} onRecsChange={() => {}} />);
    expect(screen.getByText(/All Optimizations Applied/i)).toBeInTheDocument();
  });

  it('Apply All button shows total savings (UX)', () => {
    const recs = [makeRec('a'), makeRec('b'), makeRec('c')];
    render(<Recommendations recommendations={recs} onRecsChange={() => {}} />);
    const btn = screen.getByRole('button', { name: /apply all.*save/i });
    // Each rec is 2200€ → total 6600€. Format uses de-DE locale → "6.600 €"
    expect(btn.textContent).toMatch(/6\.600.*€/);
  });

  it('groups recommendations by category with totals (UX)', () => {
    const recs: Recommendation[] = [
      { ...makeRec('f1'), type: 'move_facility' },
      { ...makeRec('m1'), type: 'restage_material' },
      { ...makeRec('m2'), type: 'restage_material' },
      { ...makeRec('e1'), type: 'reschedule_equipment' },
    ];
    render(<Recommendations recommendations={recs} onRecsChange={() => {}} />);
    expect(screen.getByText(/Facility placement/i)).toBeInTheDocument();
    expect(screen.getByText(/Material staging/i)).toBeInTheDocument();
    expect(screen.getByText(/Equipment scheduling/i)).toBeInTheDocument();
  });

  it('groups release_equipment under Equipment scheduling (audit fix)', () => {
    const recs: Recommendation[] = [
      { ...makeRec('e1'), type: 'release_equipment' },
    ];
    render(<Recommendations recommendations={recs} onRecsChange={() => {}} />);
    expect(screen.getByText(/Equipment scheduling/i)).toBeInTheDocument();
    // NOT in the catch-all "Other" bucket.
    expect(screen.queryByText(/^Other$/i)).toBeNull();
  });

  it('groups add_equipment under Vertical transport (audit fix)', () => {
    const recs: Recommendation[] = [
      { ...makeRec('v1'), type: 'add_equipment' },
    ];
    render(<Recommendations recommendations={recs} onRecsChange={() => {}} />);
    expect(screen.getByText(/Vertical transport/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Other$/i)).toBeNull();
  });

  it('shows a success receipt on each applied row (UX feedback)', () => {
    const recs: Recommendation[] = [
      { ...makeRec('a', true), type: 'move_facility',
        from_position: { x: 0, y: 0 }, to_position: { x: 30, y: 40 } },
    ];
    render(<Recommendations recommendations={recs} onRecsChange={() => {}} />);
    // Aggregate header
    expect(screen.getByText(/Applied \(1\)/i)).toBeInTheDocument();
    // Per-row "what changed" line
    expect(screen.getByText(/Moved 50m to a better location/i)).toBeInTheDocument();
  });

  it('calls onApplied with the rec after a single Apply click', async () => {
    const recs = [makeRec('a')];
    const onApplied = vi.fn();
    render(
      <Recommendations recommendations={recs} onRecsChange={() => {}} onApplied={onApplied} />,
    );
    await act(async () => {
      fireEvent.click(screen.getByText('Apply'));
    });
    await flushAsync();
    expect(onApplied).toHaveBeenCalledWith(recs[0]);
  });

  it('pushes a success toast after a single Apply click', async () => {
    const { _resetToasts, subscribeToasts } = await import('../../utils/toasts');
    _resetToasts();
    let snapshot: ReadonlyArray<{ title: string; subtitle?: string }> = [];
    const unsub = subscribeToasts((list) => { snapshot = list; });

    const recs = [makeRec('a')];
    render(<Recommendations recommendations={recs} onRecsChange={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByText('Apply'));
    });
    await flushAsync();

    expect(snapshot.length).toBeGreaterThan(0);
    expect(snapshot[0].title).toMatch(/Saved 2\.200/);
    expect(snapshot[0].subtitle).toMatch(/a/);
    unsub();
    _resetToasts();
  });
});
