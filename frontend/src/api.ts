export type Role = "jeweller" | "karigar";

const key = (role: Role) => `khata_${role}`;

export function getToken(role: Role): string | null {
  try {
    return localStorage.getItem(key(role));
  } catch {
    return memory[role] ?? null;
  }
}

const memory: Partial<Record<Role, string>> = {};

export function setToken(role: Role, token: string | null) {
  memory[role] = token ?? undefined;
  try {
    if (token) localStorage.setItem(key(role), token);
    else localStorage.removeItem(key(role));
  } catch {
    /* private mode: memory only */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: unknown; role?: Role; form?: FormData } = {},
): Promise<T> {
  const role = opts.role ?? "jeweller";
  const headers: Record<string, string> = {};
  const token = getToken(role);
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method: opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET"),
    headers,
    body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not json */
    }
    if (res.status === 401) setToken(role, null);
    throw new ApiError(res.status, msg);
  }
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export async function upload(file: File, role: Role = "jeweller"): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const r = await api<{ url: string }>("/api/uploads", { form, role });
  return r.url;
}
