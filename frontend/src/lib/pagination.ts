export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export async function allPages<T>(fetchPage: (offset: number) => Promise<Page<T>>) {
  const all: T[] = [];
  for (let offset = 0; ; ) {
    const page = await fetchPage(offset);
    if (!Number.isInteger(page.limit) || page.limit <= 0) {
      throw new Error('The server returned an invalid page size. Please try again.');
    }
    all.push(...page.items);
    offset += page.limit;
    if (offset >= page.total) {
      return all;
    }
  }
}
