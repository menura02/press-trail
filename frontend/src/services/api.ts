async function request(path: string, init?: RequestInit) {
  const response = await fetch("/api" + path, init);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail :
      response.status === 422 ? "Formdaki alanları kontrol edin." : "Sunucu isteği tamamlayamadı.");
  }
  return response;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function downloadHtml(path: string, value: unknown, filename: string) {
  const response = await request(path, json("POST", value));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function json(method: "POST" | "PUT", value: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) };
}

