export type ValidationIssue = { loc: (string | number)[]; msg: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly issues: ValidationIssue[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function validationIssues(body: unknown): ValidationIssue[] {
  if (!body || typeof body !== 'object' || !('detail' in body) || !Array.isArray(body.detail)) {
    return [];
  }
  return body.detail.filter(
    (issue: unknown): issue is ValidationIssue =>
      !!issue &&
      typeof issue === 'object' &&
      'msg' in issue &&
      typeof issue.msg === 'string' &&
      'loc' in issue &&
      Array.isArray(issue.loc),
  );
}

function relevantIssues(issues: ValidationIssue[]): ValidationIssue[] {
  const ingestion = issues.filter((issue) =>
    issue.loc.some((part) =>
      typeof part === 'string' && part.toLowerCase().includes('ingestion'),
    ),
  );
  return ingestion.length ? ingestion : issues;
}

function issueField(issue: ValidationIssue): string {
  const ocr = issue.loc.lastIndexOf('ocr');
  if (ocr >= 0) {
    const name: Record<string, string> = {
      dpi: 'OCR resolution (DPI)',
      max_pages: 'Maximum OCR pages',
      timeout_seconds: 'Per-page timeout',
      languages: 'OCR languages',
    };
    return `Extract · ${name[String(issue.loc[ocr + 1])] ?? String(issue.loc[ocr + 1])}`;
  }
  return issue.loc
    .filter((part) => typeof part === 'string' && !['body', 'ingestion', 'execution'].includes(part))
    .slice(-2)
    .join(' · ');
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    if (typeof body.detail === 'string') {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      const messages = relevantIssues(validationIssues(body)).map((issue) => {
        const field = issueField(issue);
        return field ? `${field}: ${issue.msg}` : issue.msg;
      });
      if (messages.length) {
        return messages.slice(0, 5).join(' ') + (messages.length > 5 ? ` ${messages.length - 5} more settings need review.` : '');
      }
    }
  }
  if (status === 422) {
    return 'Check the submitted fields and settings, then try again.';
  }
  if (status === 503) {
    return 'The service is temporarily unavailable. Please try again.';
  }
  return 'The request failed. Please try again.';
}

/** Fetch JSON from the application API; the timeout includes reading the response body. */
export async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 12000,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) {
    abort();
  }
  options.signal?.addEventListener('abort', abort, { once: true });
  const timeout = window.setTimeout(abort, timeoutMs);
  try {
    const response = await fetch(`/api${path}`, { ...options, signal: controller.signal });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      throw new ApiError(
        errorMessage(response.status, body),
        response.status,
        validationIssues(body),
      );
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (options.signal?.aborted) {
      throw error;
    }
    if (controller.signal.aborted) {
      throw new Error('The request timed out. Please try again.');
    }
    throw new Error('Could not reach the server. Check your connection and try again.');
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abort);
  }
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
