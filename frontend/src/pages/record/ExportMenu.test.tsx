import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ExportMenu from './ExportMenu';
import { API_BASE } from '../../services/api';

describe('ExportMenu', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('lists exports and hides timesheets for non-managers', () => {
    render(<ExportMenu isManager={false} />);
    fireEvent.click(screen.getByText('Export ▾'));
    expect(screen.getByText('Cost report')).toBeInTheDocument();
    expect(screen.getByText('Equipment utilization')).toBeInTheDocument();
    expect(screen.queryByText('Timesheets')).toBeNull();
  });

  it('shows timesheets for managers and links to the export endpoints', () => {
    render(<ExportMenu isManager />);
    fireEvent.click(screen.getByText('Export ▾'));
    expect(screen.getByText('Timesheets')).toBeInTheDocument();
    const costs = screen.getByText('Cost report').closest('a')!;
    expect(costs).toHaveAttribute('href', `${API_BASE}/api/record/exports/costs.csv`);
    expect(costs).toHaveAttribute('download');
    const timesheets = screen.getByText('Timesheets').closest('a')!;
    expect(timesheets.getAttribute('href')).toContain('/api/record/exports/timesheets.csv');
  });
});
