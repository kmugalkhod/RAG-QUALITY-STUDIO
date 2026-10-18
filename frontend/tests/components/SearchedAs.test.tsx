import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SearchedAs, searchedAsParts } from '../../src/components/SearchedAs';

const ROW = '| Race and year | Number |\n| --- | --- |\n| 2015 | 125,800 |';
const PREFIX = 'Section: APPENDIX A > Table A-2\n\n';

describe('Searched as', () => {
  it('shows the prefix and the searched text of a table row', () => {
    render(
      <SearchedAs
        label="Chunk 4 searched as"
        text={ROW}
        prefix={PREFIX}
        embeddingText={`${PREFIX}ALL RACES. Race and year: 2015; Number: 125,800`}
      />,
    );
    const section = screen.getByRole('region', { name: 'Chunk 4 searched as' });
    expect(section).toHaveTextContent('Searched as');
    expect(section.querySelector('pre')?.textContent).toBe(
      'Section: APPENDIX A > Table A-2\n\nALL RACES. Race and year: 2015; Number: 125,800',
    );
  });

  it('names only the prefix when the rest is the passage text', () => {
    expect(searchedAsParts('Body', `${PREFIX}Body`, PREFIX)).toEqual({
      prefix: 'Section: APPENDIX A > Table A-2',
      body: null,
    });
    render(
      <SearchedAs
        label="Chunk 1 searched as"
        text="Body"
        prefix={PREFIX}
        embeddingText={`${PREFIX}Body`}
      />,
    );
    expect(screen.getByRole('region', { name: 'Chunk 1 searched as' })).toHaveTextContent(
      'Searched as · section prefix, then the passage text',
    );
  });

  it('shows nothing when a passage is searched as its own text', () => {
    expect(searchedAsParts('Body', 'Body', '')).toBeNull();
    expect(searchedAsParts('Body', undefined, undefined)).toBeNull();
    const { container } = render(
      <SearchedAs label="x" text="Body" prefix="" embeddingText="Body" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows searched text that has no prefix', () => {
    expect(searchedAsParts(ROW, 'Race and year: 2015', '')).toEqual({
      prefix: '',
      body: 'Race and year: 2015',
    });
  });
});
