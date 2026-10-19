const TOKEN_KEY = "valuationlab-token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers });
  if (response.status === 401 && !path.startsWith("/auth/")) {
    clearToken();
    window.location.assign("/login");
  }
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      message = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {
      message = await response.text();
    }
    throw new ApiError(response.status, message);
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("spreadsheet") || type.includes("octet-stream")) {
    return (await response.blob()) as T;
  }
  return response.json() as Promise<T>;
}
