import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { WebsiteSettings } from '../../../src/features/ingestion-pipelines/components/SourceSettings';
import {
  defaultWebsite,
  serverFieldErrors,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type { WebsiteConfig } from '../../../src/features/ingestion-pipelines/model';

let latest: WebsiteConfig;

function Harness({
  initial,
  fieldErrors,
}: {
  initial: WebsiteConfig;
  fieldErrors?: Record<string, string>;
}) {
  const [config, setConfig] = useState(initial);
  latest = config;
  return (
    <WebsiteSettings
      config={config}
      fieldErrors={fieldErrors}
      update={(next) => {
        latest = next;
        setConfig(next);
      }}
    />
  );
}

const labels = () =>
  Array.from(document.querySelectorAll('input, textarea, select')).map(
    (control) => control.closest('label')?.childNodes[0]?.textContent?.trim() ?? '',
  );

test('shows only the settings that apply to each discovery mode', () => {
  render(<Harness initial={defaultWebsite()} />);
  expect(labels()).toEqual([
    'Discovery mode',
    'Start URL',
    'Maximum pages',
    'Maximum crawl depth',
    'Include path prefixes (one per line)',
    'Exclude path prefixes (one per line)',
    'Allowed origins (one per line)',
    'Crawl speed (requests per second)',
  ]);
  expect(screen.queryByText(/user agent/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/robots/i)).toBeInTheDocument();
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Discovery mode'), { target: { value: 'single_url' } });
  expect(labels()).toEqual(['Discovery mode', 'Page URL', 'Allowed origins (one per line)']);

  fireEvent.change(screen.getByLabelText('Discovery mode'), { target: { value: 'sitemap' } });
  expect(labels()).toEqual([
    'Discovery mode',
    'Sitemap URL',
    'Maximum pages',
    'Include path prefixes (one per line)',
    'Exclude path prefixes (one per line)',
    'Allowed origins (one per line)',
    'Crawl speed (requests per second)',
  ]);

  fireEvent.change(screen.getByLabelText('Discovery mode'), { target: { value: 'url_list' } });
  expect(labels()).toEqual([
    'Discovery mode',
    'URLs (one per line)',
    'Maximum pages',
    'Allowed origins (one per line)',
    'Crawl speed (requests per second)',
  ]);
});

test('derives include prefixes and origins from the start URL until the user edits them', () => {
  render(<Harness initial={defaultWebsite()} />);
  const start = screen.getByLabelText('Start URL');
  fireEvent.change(start, { target: { value: 'https://docs.example/guide/intro' } });
  expect(latest.include_path_prefixes).toEqual(['/guide/']);
  expect(latest.allowed_origins).toEqual(['https://docs.example']);

  fireEvent.change(start, { target: { value: 'https://docs.example/' } });
  expect(latest.include_path_prefixes).toEqual([]);

  fireEvent.change(start, { target: { value: 'https://docs.example/api/v2/' } });
  expect(latest.include_path_prefixes).toEqual(['/api/v2/']);

  fireEvent.change(screen.getByLabelText('Include path prefixes (one per line)'), {
    target: { value: '/api/' },
  });
  fireEvent.change(start, { target: { value: 'https://docs.example/blog/post' } });
  expect(latest.include_path_prefixes).toEqual(['/api/']);
});

test('warns when a crawl start URL without a trailing slash widens the scope', () => {
  render(<Harness initial={defaultWebsite()} />);
  const start = screen.getByLabelText('Start URL');
  fireEvent.change(start, { target: { value: 'https://docs.python.org/3/tutorial' } });
  expect(latest.include_path_prefixes).toEqual(['/3/']);
  expect(screen.getByRole('status')).toHaveTextContent(
    'This URL has no trailing slash, so the crawl covers every page under /3/. Add a slash to crawl only /3/tutorial/.',
  );
  expect(start).toHaveAccessibleDescription(/no trailing slash/);

  fireEvent.click(screen.getByRole('button', { name: 'Add trailing slash' }));
  expect(latest.selection).toEqual({
    mode: 'crawl',
    start_url: 'https://docs.python.org/3/tutorial/',
  });
  expect(latest.include_path_prefixes).toEqual(['/3/tutorial/']);
  expect(screen.queryByRole('status')).toBeNull();

  // A file-like page is a deliberate start point; no warning.
  fireEvent.change(start, { target: { value: 'https://docs.python.org/3/tutorial/index.html' } });
  expect(screen.queryByRole('status')).toBeNull();
});

test('maps real server validation issues to Website fields', () => {
  expect(
    serverFieldErrors([
      // Pydantic: the discriminated source config, then the field.
      {
        loc: ['body', 'execution', 'nodes', 0, 'config', 'website', 'max_pages'],
        msg: 'The URL list has 60 URLs; raise maximum pages or remove URLs.',
      },
      // The server's crawl-time check is shaped the same way.
      {
        loc: ['execution', 'nodes', 0, 'config', 'website', 'requests_per_second'],
        msg: 'Lower maximum pages or raise crawl speed.',
      },
      { loc: ['body', 'execution', 'nodes', 0, 'config', 'website', 'selection'], msg: 'x' },
    ]),
  ).toEqual({
    'website.max_pages': 'The URL list has 60 URLs; raise maximum pages or remove URLs.',
    'website.requests_per_second': 'Lower maximum pages or raise crawl speed.',
  });
});

test('shows a server field error on maximum pages', () => {
  render(
    <Harness
      initial={{
        ...defaultWebsite(),
        selection: { mode: 'url_list', urls: ['https://a.example/1', 'https://a.example/2'] },
        max_pages: 1,
      }}
      fieldErrors={{ 'website.max_pages': 'The URL list has 2 URLs; raise maximum pages.' }}
    />,
  );
  expect(screen.getByRole('alert')).toHaveTextContent('The URL list has 2 URLs');
  expect(screen.getByLabelText('Maximum pages')).toHaveAttribute('aria-invalid', 'true');
});

test('origins keep following the URL when it is retyped one key at a time', () => {
  render(<Harness initial={defaultWebsite()} />);
  const start = screen.getByLabelText('Start URL');
  fireEvent.change(start, { target: { value: 'https://a.example/docs/intro' } });
  expect(latest.allowed_origins).toEqual(['https://a.example']);
  const keys = ['h', 'ht', 'htt', 'http', 'https', 'https:', 'https:/', 'https://', 'https://b'];
  for (const value of [
    ...keys,
    'https://b.',
    'https://b.e',
    'https://b.example',
    'https://b.example/',
  ]) {
    fireEvent.change(start, { target: { value } });
  }
  expect(latest.selection).toEqual({ mode: 'crawl', start_url: 'https://b.example/' });
  expect(latest.allowed_origins).toEqual(['https://b.example']);
});

test('origins follow the URL after a discovery-mode switch', () => {
  render(<Harness initial={defaultWebsite()} />);
  fireEvent.change(screen.getByLabelText('Start URL'), {
    target: { value: 'https://a.example/docs/' },
  });
  fireEvent.change(screen.getByLabelText('Discovery mode'), { target: { value: 'single_url' } });
  fireEvent.change(screen.getByLabelText('Page URL'), {
    target: { value: 'https://b.example/page' },
  });
  expect(latest.allowed_origins).toEqual(['https://b.example']);
});

test('a deliberately cleared include prefix stays cleared across URL edits', () => {
  render(<Harness initial={defaultWebsite()} />);
  const start = screen.getByLabelText('Start URL');
  fireEvent.change(start, { target: { value: 'https://a.example/docs/intro' } });
  fireEvent.change(screen.getByLabelText('Include path prefixes (one per line)'), {
    target: { value: '' },
  });
  expect(latest.include_path_prefixes).toEqual([]);
  fireEvent.change(start, { target: { value: 'https://a.example/' } });
  fireEvent.change(start, { target: { value: 'https://a.example/api/v2/' } });
  expect(latest.include_path_prefixes).toEqual([]);
});

test('Enter in the URL list textarea keeps the new line', () => {
  render(<Harness initial={{ ...defaultWebsite(), selection: { mode: 'url_list', urls: [] } }} />);
  const area = screen.getByLabelText('URLs (one per line)') as HTMLTextAreaElement;
  fireEvent.change(area, { target: { value: 'https://a.example/1' } });
  fireEvent.change(area, { target: { value: 'https://a.example/1\n' } });
  expect(area.value).toBe('https://a.example/1\n');
});

test('keeps deriving origins for a saved pipeline and after the editor reloads it', () => {
  // The server returns origins with a trailing slash, and a save hands the
  // editor a fresh config object without remounting the settings.
  function Reloadable() {
    const [config, setConfig] = useState<WebsiteConfig>({
      ...defaultWebsite(),
      selection: { mode: 'crawl', start_url: 'https://a.example/docs/' },
      allowed_origins: ['https://a.example/'],
      include_path_prefixes: ['/docs/'],
    });
    latest = config;
    return (
      <>
        <WebsiteSettings
          config={config}
          update={(next) => {
            latest = next;
            setConfig(next);
          }}
        />
        <button
          type="button"
          onClick={() =>
            setConfig({ ...config, allowed_origins: config.allowed_origins.map((o) => `${o}/`) })
          }
        >
          Reload saved
        </button>
      </>
    );
  }
  render(<Reloadable />);
  const start = screen.getByLabelText('Start URL');
  fireEvent.change(start, { target: { value: 'https://b.example/guide/' } });
  expect(latest.allowed_origins).toEqual(['https://b.example']);
  expect(latest.include_path_prefixes).toEqual(['/guide/']);

  fireEvent.click(screen.getByRole('button', { name: 'Reload saved' }));
  fireEvent.change(start, { target: { value: 'https://c.example/api/' } });
  expect(latest.allowed_origins).toEqual(['https://c.example']);
  expect(latest.include_path_prefixes).toEqual(['/api/']);
});
