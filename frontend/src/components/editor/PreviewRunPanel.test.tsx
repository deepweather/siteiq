import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { PreviewRunPanel } from './PreviewRunPanel';
import { blankProjectDocument, type PreviewResponse } from '../../services/projectsApi';
import * as projectsApi from '../../services/projectsApi';
import { ApiError } from '../../services/api';

function happyResponse(): PreviewResponse {
  return {
    sim_time: 7200,
    sim_day: 1,
    site: { id: 's', name: 'Preview Site', width: 100, height: 80, zones: [], levels: [] },
    assets: [{ id: 'w1', type: 'worker', subtype: 'general', x: 10, y: 10 }],
    waste: {
      toilet_walk_daily: 100,
      toilet_walk_monthly: 2200,
      material_handling_daily: 50,
      material_handling_monthly: 1100,
      equipment_idle_daily: 200,
      equipment_idle_monthly: 4400,
      vertical_transport_daily: 0,
      vertical_transport_monthly: 0,
      total_daily: 350,
      total_monthly: 7700,
    },
    recommendations: [
      { id: 'r1', type: 'move_facility', title: 'Move toilet-1', description: 'Cuts walking', target_asset_id: 'toilet-1', daily_savings: 30, monthly_savings: 660 },
      { id: 'r2', type: 'reschedule_equipment', title: 'Reschedule crane-1', description: 'Lower idle', target_asset_id: 'crane-1', daily_savings: 50, monthly_savings: 1100 },
    ],
  };
}

describe('PreviewRunPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading state, then waste + top recommendations', async () => {
    const doc = blankProjectDocument('demo', 'Demo');
    const spy = vi.spyOn(projectsApi, 'previewProject').mockResolvedValue(happyResponse());
    render(
      <PreviewRunPanel
        projectId="p1"
        document={doc}
        documentVersion={1}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/Running simulation/i)).toBeDefined();
    await waitFor(() => screen.getByTestId('preview-waste'));
    expect(screen.getByText('Move toilet-1')).toBeDefined();
    expect(screen.getByText('Reschedule crane-1')).toBeDefined();
    // Snapshot block shows day + sim-time.
    expect(screen.getByText(/Day 1/)).toBeDefined();
    expect(spy).toHaveBeenCalledWith('p1', doc);
  });

  it('caps the recommendations list at 5 entries', async () => {
    const doc = blankProjectDocument('demo', 'Demo');
    const many = happyResponse();
    many.recommendations = Array.from({ length: 8 }, (_, i) => ({
      id: `r${i}`, type: 'move_facility',
      title: `Recommendation ${i}`, description: '',
      target_asset_id: `t${i}`, daily_savings: 1, monthly_savings: 22,
    }));
    vi.spyOn(projectsApi, 'previewProject').mockResolvedValue(many);
    render(
      <PreviewRunPanel projectId="p1" document={doc} documentVersion={1} onClose={() => {}} />,
    );
    await waitFor(() => screen.getByText('Recommendation 0'));
    expect(screen.queryByText('Recommendation 5')).toBeNull();
    expect(screen.getByText(/5 of 8/)).toBeDefined();
  });

  it('renders an error envelope when the API rejects', async () => {
    const doc = blankProjectDocument('demo', 'Demo');
    vi.spyOn(projectsApi, 'previewProject').mockRejectedValue(
      new ApiError(400, 'unknown_zone', 'Unknown zone z1', 'schedule'),
    );
    render(
      <PreviewRunPanel projectId="p1" document={doc} documentVersion={1} onClose={() => {}} />,
    );
    await waitFor(() => screen.getByText(/Preview failed/));
    expect(screen.getByText('Unknown zone z1')).toBeDefined();
    expect(screen.getByText(/schedule/)).toBeDefined();
  });

  it('calls onClose when the user clicks the × button', async () => {
    const doc = blankProjectDocument('demo', 'Demo');
    const onClose = vi.fn();
    vi.spyOn(projectsApi, 'previewProject').mockResolvedValue(happyResponse());
    render(
      <PreviewRunPanel projectId="p1" document={doc} documentVersion={1} onClose={onClose} />,
    );
    await waitFor(() => screen.getByTestId('preview-waste'));
    fireEvent.click(screen.getByLabelText('Close preview'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('auto-dismisses when the document version changes after a preview', async () => {
    const doc = blankProjectDocument('demo', 'Demo');
    const onClose = vi.fn();
    vi.spyOn(projectsApi, 'previewProject').mockResolvedValue(happyResponse());
    const { rerender } = render(
      <PreviewRunPanel projectId="p1" document={doc} documentVersion={1} onClose={onClose} />,
    );
    await waitFor(() => screen.getByTestId('preview-waste'));
    rerender(
      <PreviewRunPanel projectId="p1" document={doc} documentVersion={2} onClose={onClose} />,
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
