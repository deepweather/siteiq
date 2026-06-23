import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen, act, within } from '@testing-library/react';
import { ScheduleEditor } from './ScheduleEditor';
import { blankProjectDocument, type ProjectDocument } from '../../services/projectsApi';

function docWithSchedule(): ProjectDocument {
  const d = blankProjectDocument('demo', 'Demo');
  d.zones = [
    { id: 'z1', label: 'Block A', x: 0, y: 0, width: 30, height: 20, phase: 'structural', phase_progress: 0.5, level_id: 'L0' },
    { id: 'z2', label: 'Block B', x: 30, y: 0, width: 30, height: 20, phase: 'foundation', phase_progress: 0.2, level_id: 'L0' },
  ];
  d.schedule = [
    { zone_id: 'z1', phase: 'foundation', start_day: 1, end_day: 30, trades_required: [] },
    { zone_id: 'z1', phase: 'structural', start_day: 31, end_day: 90, trades_required: [] },
  ];
  return d;
}

/** Mimic the `patch` contract from `useProjectDraft` so the editor's
 *  reducer flow is exercised end-to-end inside the test. */
function patcher(doc: ProjectDocument) {
  const state = { current: doc };
  return {
    get current() { return state.current; },
    patch: (u: (d: ProjectDocument) => ProjectDocument) => { state.current = u(state.current); },
  };
}

describe('ScheduleEditor', () => {
  it('renders one row per zone, ordered like document.zones', () => {
    render(<ScheduleEditor document={docWithSchedule()} patch={() => {}} />);
    const rows = screen.getAllByTestId(/^schedule-row-/);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveProperty('dataset.testid', 'schedule-row-z1');
    expect(rows[1]).toHaveProperty('dataset.testid', 'schedule-row-z2');
  });

  it('paints existing schedule blocks with the right phase data', () => {
    render(<ScheduleEditor document={docWithSchedule()} patch={() => {}} />);
    const first = screen.getByTestId('schedule-block-z1-0');
    expect(first.dataset.phase).toBe('foundation');
    expect(first.dataset.startDay).toBe('1');
    expect(first.dataset.endDay).toBe('30');
  });

  it('clicking "+ Phase" then picking a phase appends an entry past the current max', () => {
    const p = vi.fn((u: (d: ProjectDocument) => ProjectDocument) => {
      const out = u(docWithSchedule());
      // Re-throw via spy.calls[0][0]
      p.lastDoc = out;
    }) as unknown as ((u: (d: ProjectDocument) => ProjectDocument) => void) & { lastDoc?: ProjectDocument };
    render(<ScheduleEditor document={docWithSchedule()} patch={p} />);
    fireEvent.click(screen.getByTestId('schedule-add-z1'));
    fireEvent.click(within(screen.getByTestId('schedule-phase-picker')).getByText('MEP Rough-in'));
    expect(p).toHaveBeenCalled();
    const out = p.lastDoc!;
    const z1 = out.schedule.filter((s) => s.zone_id === 'z1');
    expect(z1).toHaveLength(3);
    const added = z1[2];
    expect(added.phase).toBe('mep_roughin');
    expect(added.start_day).toBe(91); // currentMax (90) + 1
    expect(added.end_day).toBe(121);  // start + 30
  });

  it('delete (×) removes the targeted entry', () => {
    const p = vi.fn((u: (d: ProjectDocument) => ProjectDocument) => {
      p.lastDoc = u(docWithSchedule());
    }) as unknown as ((u: (d: ProjectDocument) => ProjectDocument) => void) & { lastDoc?: ProjectDocument };
    render(<ScheduleEditor document={docWithSchedule()} patch={p} />);
    fireEvent.click(screen.getByTestId('schedule-delete-z1-0'));
    expect(p.lastDoc!.schedule.filter((s) => s.zone_id === 'z1')).toHaveLength(1);
    expect(p.lastDoc!.schedule[0].phase).toBe('structural');
  });

  it('drag-move on the block commits ONE patch with shifted start/end', () => {
    const p = vi.fn((u: (d: ProjectDocument) => ProjectDocument) => {
      p.lastDoc = u(docWithSchedule());
    }) as unknown as ((u: (d: ProjectDocument) => ProjectDocument) => void) & { lastDoc?: ProjectDocument };
    render(<ScheduleEditor document={docWithSchedule()} patch={p} />);
    const block = screen.getByTestId('schedule-block-z1-0');
    // Stub the row's bounding box so daysPerPx math is deterministic.
    // totalDays = max(60, 90 + 30) = 120; we choose 120px so 1px == 1 day.
    const row = block.parentElement as HTMLElement;
    row.getBoundingClientRect = () => ({
      x: 0, y: 0, top: 0, left: 0, right: 120, bottom: 7,
      width: 120, height: 7, toJSON: () => ({}),
    });

    fireEvent.mouseDown(block, { clientX: 0 });
    act(() => {
      fireEvent.mouseMove(window, { clientX: 10 }); // +10 days
      fireEvent.mouseUp(window);
    });

    expect(p).toHaveBeenCalledTimes(1);
    const moved = p.lastDoc!.schedule.find((s) => s.zone_id === 'z1' && s.phase === 'foundation')!;
    expect(moved.start_day).toBe(11);
    expect(moved.end_day).toBe(40);
  });

  it('left-handle drag only adjusts start_day; bounds clamp to ≥1', () => {
    const p = vi.fn((u: (d: ProjectDocument) => ProjectDocument) => {
      p.lastDoc = u(docWithSchedule());
    }) as unknown as ((u: (d: ProjectDocument) => ProjectDocument) => void) & { lastDoc?: ProjectDocument };
    render(<ScheduleEditor document={docWithSchedule()} patch={p} />);
    const handle = screen.getByTestId('schedule-handle-left-z1-0');
    const row = handle.closest('[data-testid="schedule-block-z1-0"]')!.parentElement as HTMLElement;
    row.getBoundingClientRect = () => ({
      x: 0, y: 0, top: 0, left: 0, right: 120, bottom: 7,
      width: 120, height: 7, toJSON: () => ({}),
    });

    // Drag the left handle far to the left → start would be negative;
    // implementation must clamp to 1.
    fireEvent.mouseDown(handle, { clientX: 100 });
    act(() => {
      fireEvent.mouseMove(window, { clientX: 0 }); // -100 days
      fireEvent.mouseUp(window);
    });

    const entry = p.lastDoc!.schedule.find((s) => s.zone_id === 'z1' && s.phase === 'foundation')!;
    expect(entry.start_day).toBe(1);
    // end_day must not have changed.
    expect(entry.end_day).toBe(30);
  });

  it('right-handle drag only adjusts end_day; never shrinks below start+1', () => {
    const p = vi.fn((u: (d: ProjectDocument) => ProjectDocument) => {
      p.lastDoc = u(docWithSchedule());
    }) as unknown as ((u: (d: ProjectDocument) => ProjectDocument) => void) & { lastDoc?: ProjectDocument };
    render(<ScheduleEditor document={docWithSchedule()} patch={p} />);
    const handle = screen.getByTestId('schedule-handle-right-z1-0');
    const row = handle.closest('[data-testid="schedule-block-z1-0"]')!.parentElement as HTMLElement;
    row.getBoundingClientRect = () => ({
      x: 0, y: 0, top: 0, left: 0, right: 120, bottom: 7,
      width: 120, height: 7, toJSON: () => ({}),
    });

    fireEvent.mouseDown(handle, { clientX: 100 });
    act(() => {
      // huge left drag — end_day would go below start_day.
      fireEvent.mouseMove(window, { clientX: 0 });
      fireEvent.mouseUp(window);
    });

    const entry = p.lastDoc!.schedule.find((s) => s.zone_id === 'z1' && s.phase === 'foundation')!;
    expect(entry.start_day).toBe(1);
    expect(entry.end_day).toBeGreaterThan(entry.start_day);
  });

  it('reducer chain produces a single committed state from start to finish', () => {
    // End-to-end check: connect a real patcher to the component and
    // verify the final state after add → drag-move → delete.
    const p = patcher(docWithSchedule());
    function Harness() {
      return <ScheduleEditor document={p.current} patch={p.patch} />;
    }
    const { rerender } = render(<Harness />);

    fireEvent.click(screen.getByTestId('schedule-add-z2'));
    fireEvent.click(within(screen.getByTestId('schedule-phase-picker')).getByText('Structural'));
    rerender(<Harness />);
    expect(p.current.schedule.some((s) => s.zone_id === 'z2' && s.phase === 'structural')).toBe(true);

    fireEvent.click(screen.getByTestId('schedule-delete-z2-0'));
    rerender(<Harness />);
    expect(p.current.schedule.some((s) => s.zone_id === 'z2')).toBe(false);
  });
});
