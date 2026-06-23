import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LevelSwitcher } from './LevelSwitcher';
import type { Level } from '../../types/site';

const levels: Level[] = [
  { id: 'L-1', name: 'UG1', elevation_m: -3.0, order: -1 },
  { id: 'L0', name: 'EG', elevation_m: 0.0, order: 0 },
  { id: 'L1', name: '1. OG', elevation_m: 3.5, order: 1 },
];

describe('LevelSwitcher', () => {
  it('renders one button per level, sorted top → bottom by order desc', () => {
    const { container } = render(
      <LevelSwitcher levels={levels} activeLevel="L0" onLevelChange={() => {}} />,
    );
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBe(3);
    // Top row is the highest order ("1. OG"), bottom is "UG1".
    expect(buttons[0].textContent).toContain('1. OG');
    expect(buttons[1].textContent).toContain('EG');
    expect(buttons[2].textContent).toContain('UG1');
  });

  it('highlights the active level', () => {
    const { container } = render(
      <LevelSwitcher levels={levels} activeLevel="L0" onLevelChange={() => {}} />,
    );
    const active = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('EG'),
    );
    expect(active?.className).toContain('bg-primary');
  });

  it('calls onLevelChange when a button is clicked', () => {
    const spy = vi.fn();
    render(<LevelSwitcher levels={levels} activeLevel="L0" onLevelChange={spy} />);
    fireEvent.click(screen.getByText(/1\. OG/));
    expect(spy).toHaveBeenCalledWith('L1');
  });

  it('renders nothing for single-level projects', () => {
    const { container } = render(
      <LevelSwitcher
        levels={[{ id: 'L0', name: 'EG', elevation_m: 0, order: 0 }]}
        activeLevel="L0"
        onLevelChange={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when no levels are provided', () => {
    const { container } = render(
      <LevelSwitcher levels={[]} activeLevel="L0" onLevelChange={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
