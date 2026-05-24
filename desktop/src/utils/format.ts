export function formatDate(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

export function shortId(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return value.slice(0, 8);
}
