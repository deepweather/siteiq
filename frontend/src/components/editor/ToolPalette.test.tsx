import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolPalette } from './ToolPalette';

describe('ToolPalette', () => {
  it('renders every tool category', () => {
    render(<ToolPalette tool="select" onChange={() => {}} />);
    expect(screen.getByText('Edit')).toBeDefined();
    expect(screen.getByText('Zones')).toBeDefined();
    expect(screen.getByText('Facilities')).toBeDefined();
    expect(screen.getByText('Vertical transport')).toBeDefined();
    expect(screen.getByText('Equipment')).toBeDefined();
    expect(screen.getByText('Tiefbau')).toBeDefined();
  });

  it('marks the active tool with a primary border', () => {
    render(<ToolPalette tool="add-toilet" onChange={() => {}} />);
    const button = screen.getByText('Toilet') as HTMLButtonElement;
    expect(button.className).toContain('border-primary');
  });

  it('fires onChange with the right tool id', () => {
    const onChange = vi.fn();
    render(<ToolPalette tool="select" onChange={onChange} />);
    fireEvent.click(screen.getByText('Elevator'));
    expect(onChange).toHaveBeenCalledWith('add-elevator');
  });
});
