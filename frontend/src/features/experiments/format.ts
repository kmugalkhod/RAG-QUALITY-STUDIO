export const number = (n: number | null | undefined, digits = 3) =>
  n == null ? 'Unavailable' : n.toLocaleString(undefined, { maximumFractionDigits: digits });
export const readable = (text: string) => text.replaceAll('_', ' ');
export const money = (n: number | null | undefined) =>
  n == null ? 'Unavailable' : `$${n.toFixed(6)}`;
