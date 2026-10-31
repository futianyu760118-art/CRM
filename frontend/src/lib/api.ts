/**
 * 统一 HTTP 客户端。
 * - 自动附加 Bearer Token
 * - 解包后端统一响应 { code, message, data, request_id }
 * - 401 时自动尝试一次 refresh
 */

import { useAuthStore } from '@/lib/auth-store';
import type { ApiEnvelope, TokenPair } from '@/types';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000/api/v1';

export class ApiError extends Error {
  code: number;
  status: number;
  requestId: string;
  data: unknown;

  constructor(message: string, code: number, status: number, requestId = '', data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.data = data;
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  auth?: boolean;
  skipRefresh?: boolean;
}

async function parse<T>(res: Response): Promise<ApiEnvelope<T>> {
  const text = await res.text();
  try {
    return JSON.parse(text) as ApiEnvelope<T>;
  } catch {
    throw new ApiError(text || res.statusText, res.status, res.status);
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, clear } = useAuthStore.getState();
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) {
      clear();
      return null;
    }
    const json = (await res.json()) as ApiEnvelope<TokenPair>;
    const token = json.data.access_token;
    setTokens(token, refreshToken);
    return token;
  } catch {
    clear();
    return null;
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, skipRefresh = false, headers, ...rest } = options;
  const { accessToken } = useAuthStore.getState();

  const finalHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((headers as Record<string, string>) ?? {}),
  };
  if (auth && accessToken) {
    finalHeaders.Authorization = `Bearer ${accessToken}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 401 && auth && !skipRefresh) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return request<T>(path, { ...options, skipRefresh: true });
    }
  }

  const json = await parse<T>(res);
  if (!res.ok || json.code !== 0) {
    throw new ApiError(json.message || '请求失败', json.code, res.status, json.request_id, json.data);
  }
  return json.data;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};

export function buildQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.append(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

/** 上传文件（multipart），返回文件元数据。 */
export async function uploadFile(
  file: File,
  module = 'common',
): Promise<import('@/types/business').UploadedFile> {
  const { accessToken } = useAuthStore.getState();
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${API_BASE_URL}/files/upload${buildQuery({ module })}`, {
    method: 'POST',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    body: form,
  });
  const json = (await res.json()) as ApiEnvelope<import('@/types/business').UploadedFile>;
  if (!res.ok || json.code !== 0) {
    throw new ApiError(json.message || '上传失败', json.code, res.status, json.request_id);
  }
  return json.data;
}

/** 以 multipart 方式提交任意接口（如产品资料上传，需 50MB 专用校验）。 */
export async function uploadForm<T>(path: string, form: FormData): Promise<T> {
  const { accessToken } = useAuthStore.getState();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    body: form,
  });
  const json = (await res.json()) as ApiEnvelope<T>;
  if (!res.ok || json.code !== 0) {
    throw new ApiError(json.message || '上传失败', json.code, res.status, json.request_id, json.data);
  }
  return json.data;
}

/** 受保护文件的预览地址（附带 token，便于 <img src>）。 */
export function fileUrl(fileId: string | null | undefined): string {
  if (!fileId) return '';
  const { accessToken } = useAuthStore.getState();
  return `${API_BASE_URL}/files/${fileId}${accessToken ? `?token=${accessToken}` : ''}`;
}
