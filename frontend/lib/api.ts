const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
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

export async function apiGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params).toString()}` : "";
  try {
    const response = await fetch(`${API_BASE}${path}${query}`, {
      headers: buildHeaders(),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail?.message || data.detail || "リクエストに失敗しました");
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
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: buildHeaders({ "Content-Type": "application/json", ...extraHeaders }),
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail?.message || data.detail || "リクエストに失敗しました");
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
  const query = new URLSearchParams(queryParams).toString();
  const response = await fetch(`${API_BASE}${path}?${query}`, {
    method: "POST",
    headers: buildHeaders(),
    body,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail?.message || data.detail || "リクエストに失敗しました");
  }
  return data as T;
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "PUT",
      headers: buildHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail?.message || data.detail || "リクエストに失敗しました");
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
    const response = await fetch(`${API_BASE}${path}`, {
      method: "DELETE",
      headers: buildHeaders(),
    });
    if (response.status === 204) {
      return undefined as T;
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail?.message || data.detail || "リクエストに失敗しました");
    }
    return data as T;
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("サーバーに接続できません。APIサーバーが起動しているか確認してください。");
    }
    throw err;
  }
}
