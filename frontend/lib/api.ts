const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("refresh_token");
}

function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...extra,
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

let isRefreshing = false;
let refreshPromise: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      isRefreshing = false;
    }
  })();

  return refreshPromise;
}

function shouldRedirectLogin(path: string): boolean {
  return !path.startsWith("/auth/");
}

async function handle401(path: string): Promise<boolean> {
  const refreshed = await tryRefreshToken();
  if (!refreshed) {
    if (shouldRedirectLogin(path) && typeof window !== "undefined") {
      localStorage.removeItem("token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
    }
    return false;
  }
  return true;
}

function extractError(data: unknown): string {
  if (typeof data === "object" && data !== null) {
    const d = data as Record<string, unknown>;
    if (d.detail && typeof d.detail === "object") {
      const detail = d.detail as Record<string, unknown>;
      if (typeof detail.message === "string") return detail.message;
    }
    if (typeof d.detail === "string") return d.detail;
  }
  return "リクエストに失敗しました";
}

export async function apiGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params).toString()}` : "";
  try {
    let response = await fetch(`${API_BASE}${path}${query}`, {
      headers: buildHeaders(),
    });
    if (response.status === 401) {
      const refreshed = await handle401(path);
      if (refreshed) {
        response = await fetch(`${API_BASE}${path}${query}`, {
          headers: buildHeaders(),
        });
      }
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(extractError(data));
    }
    return data as T;
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("サーバーに接続できません。APIサーバーが起動しているか確認してください。");
    }
    throw err;
  }
}

export async function apiPost<T>(path: string, body: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  try {
    let response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: buildHeaders({ "Content-Type": "application/json", ...extraHeaders }),
      body: JSON.stringify(body),
    });
    if (response.status === 401) {
      const refreshed = await handle401(path);
      if (refreshed) {
        response = await fetch(`${API_BASE}${path}`, {
          method: "POST",
          headers: buildHeaders({ "Content-Type": "application/json", ...extraHeaders }),
          body: JSON.stringify(body),
        });
      }
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(extractError(data));
    }
    return data as T;
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("サーバーに接続できません。APIサーバーが起動しているか確認してください。");
    }
    throw err;
  }
}

export async function apiPostMultipart<T>(path: string, queryParams: Record<string, string>, body: FormData): Promise<T> {
  try {
    const query = new URLSearchParams(queryParams).toString();
    let response = await fetch(`${API_BASE}${path}?${query}`, {
      method: "POST",
      headers: buildHeaders(),
      body,
    });
    if (response.status === 401) {
      const refreshed = await handle401(path);
      if (refreshed) {
        response = await fetch(`${API_BASE}${path}?${query}`, {
          method: "POST",
          headers: buildHeaders(),
          body,
        });
      }
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(extractError(data));
    }
    return data as T;
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("サーバーに接続できません。APIサーバーが起動しているか確認してください。");
    }
    throw err;
  }
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  try {
    let response = await fetch(`${API_BASE}${path}`, {
      method: "PUT",
      headers: buildHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.status === 401) {
      const refreshed = await handle401(path);
      if (refreshed) {
        response = await fetch(`${API_BASE}${path}`, {
          method: "PUT",
          headers: buildHeaders({ "Content-Type": "application/json" }),
          body: body ? JSON.stringify(body) : undefined,
        });
      }
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(extractError(data));
    }
    return data as T;
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("サーバーに接続できません。APIサーバーが起動しているか確認してください。");
    }
    throw err;
  }
}

export async function apiDelete<T>(path: string): Promise<T> {
  try {
    let response = await fetch(`${API_BASE}${path}`, {
      method: "DELETE",
      headers: buildHeaders(),
    });
    if (response.status === 401) {
      const refreshed = await handle401(path);
      if (refreshed) {
        response = await fetch(`${API_BASE}${path}`, {
          method: "DELETE",
          headers: buildHeaders(),
        });
      }
    }
    if (response.status === 204) {
      return undefined as T;
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(extractError(data));
    }
    return data as T;
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("サーバーに接続できません。APIサーバーが起動しているか確認してください。");
    }
    throw err;
  }
}
