import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import { LevelManager } from './LevelManager';
import { blankProjectDocument, type ProjectDocument } from '../../services/projectsApi';
import * as projectsApi from '../../services/projectsApi';

function docWithLevels(): ProjectDocument {
  const d = blankProjectDocument('demo', 'Demo');
  d.levels = [
    { id: 'L-1', name: 'UG1', elevation_m: -3, order: -1 },
    { id: 'L0', name: 'EG', elevation_m: 0, order: 0 },
    { id: 'L1', name: '1. OG', elevation_m: 3.5, order: 1 },
  ];
  return d;
}

describe('LevelManager', () => {
  it('renders one row per level, top → bottom by order desc', () => {
    const { container } = render(
      <LevelManager
        document={docWithLevels()}
        activeLevel="L0"
        onActiveLevelChange={() => {}}
        patch={() => {}}
      />,
    );
    const inputs = container.querySelectorAll('input');
    expect(inputs.length).toBe(3);
    expect((inputs[0] as HTMLInputElement).value).toBe('1. OG');
    expect((inputs[1] as HTMLInputElement).value).toBe('EG');
    expect((inputs[2] as HTMLInputElement).value).toBe('UG1');
  });

  it('add button extends the level list with the next order', () => {
    const patch = vi.fn();
    render(
      <LevelManager
        document={docWithLevels()}
        activeLevel="L0"
        onActiveLevelChange={() => {}}
        patch={patch}
      />,
    );
    fireEvent.click(screen.getByText('+ Add'));
    expect(patch).toHaveBeenCalled();
    const updater = patch.mock.calls[0][0] as (d: ProjectDocument) => ProjectDocument;
    const before = docWithLevels();
    const after = updater(before);
    expect(after.levels.length).toBe(4);
    const added = after.levels[after.levels.length - 1];
    expect(added.order).toBe(2);
    expect(added.id).toBe('L2');
  });

  it('hides background buttons when projectId is omitted', () => {
    render(
      <LevelManager
        document={docWithLevels()}
        activeLevel="L0"
        onActiveLevelChange={() => {}}
        patch={() => {}}
      />,
    );
    expect(screen.queryByTestId('level-bg-input-L0')).toBeNull();
  });

  it('file input change triggers uploadLevelBackground + refetch + onProjectUpdated', async () => {
    const onProjectUpdated = vi.fn();
    const uploadSpy = vi.spyOn(projectsApi, 'uploadLevelBackground').mockResolvedValue({
      url: '/api/projects/proj-1/assets/asset-1',
      asset_id: 'asset-1',
      content_hash: 'h',
      current_version_id: 'v2',
    });
    const fresh: projectsApi.ProjectDetail = {
      ...{
        id: 'proj-1', org_id: 'o1', slug: 'demo', name: 'Demo', description: '',
        type: 'Residential', discipline: 'hochbau',
        visibility: 'private', status: 'draft',
        current_version_id: 'v2', is_owner: true,
      },
      document: docWithLevels(),
    };
    const getSpy = vi.spyOn(projectsApi, 'getProject').mockResolvedValue(fresh);

    render(
      <LevelManager
        document={docWithLevels()}
        activeLevel="L0"
        onActiveLevelChange={() => {}}
        patch={() => {}}
        projectId="proj-1"
        savedVersionId="v1"
        onProjectUpdated={onProjectUpdated}
      />,
    );

    const file = new File([new Uint8Array([1, 2, 3])], 'plan.png', { type: 'image/png' });
    const input = screen.getByTestId('level-bg-input-L0') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(uploadSpy).toHaveBeenCalledTimes(1));
    expect(uploadSpy.mock.calls[0][0]).toBe('proj-1');
    expect(uploadSpy.mock.calls[0][1]).toBe('L0');
    expect(uploadSpy.mock.calls[0][3]).toBe('v1');
    await waitFor(() => expect(onProjectUpdated).toHaveBeenCalledWith(fresh));
    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it('surfaces an upload error inline without crashing', async () => {
    const onProjectUpdated = vi.fn();
    vi.spyOn(projectsApi, 'uploadLevelBackground').mockRejectedValue(
      new (await import('../../services/api')).ApiError(413, 'file_too_large', 'Too big', 'file'),
    );
    render(
      <LevelManager
        document={docWithLevels()}
        activeLevel="L0"
        onActiveLevelChange={() => {}}
        patch={() => {}}
        projectId="proj-1"
        savedVersionId="v1"
        onProjectUpdated={onProjectUpdated}
      />,
    );
    const file = new File([new Uint8Array(3)], 'plan.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('level-bg-input-L0'), { target: { files: [file] } });
    await waitFor(() => screen.getByText('Too big'));
    expect(onProjectUpdated).not.toHaveBeenCalled();
  });

  it('rename + delete protected: cannot remove L0', () => {
    const patch = vi.fn();
    const { container } = render(
      <LevelManager
        document={docWithLevels()}
        activeLevel="L0"
        onActiveLevelChange={() => {}}
        patch={patch}
      />,
    );
    // Only 2 delete buttons (× icons): UG1 and 1.OG, not L0.
    const deleteButtons = container.querySelectorAll('button[title="Remove level"]');
    expect(deleteButtons.length).toBe(2);
  });
});
