export type Doc = { doc_id: string; name: string };

export type Source = {
  ref: number;
  doc_name: string;
  page: number;
  text: string;
  score: number;
  cited: boolean;
};

export type Answer = { answer: string; sources: Source[] };

export type Requirement = {
  id: string;
  text: string;
  page: number;
  section: string;
  category: string;
  priority: string;
};

export type Vote = { model: string; verdict: string; issue: string };

export type ReviewedRequirement = Requirement & {
  status: "accepted" | "revised" | "rejected" | "unreviewed";
  original_text: string;
  votes: Vote[];
};

export type Insights = {
  document_type: string;
  summary: string;
  parties: { name: string; role: string }[];
  key_dates: { date: string; description: string; page: number }[];
  obligations: { party: string; description: string; page: number }[];
  risks: { description: string; page: number }[];
};

export type Comparison = {
  summary: {
    ground_truth: number;
    generated: number;
    matched: number;
    precision: number;
    recall: number;
    f1: number;
    threshold: number;
  };
  matches: { truth: string; id: string; text: string; page: number; similarity: number }[];
  missed: string[];
  extra: { id: string; text: string; page: number }[];
};

export type DocState = {
  manifest: Record<string, string>;
  insights: Insights | null;
  requirements: Requirement[] | null;
  review: ReviewedRequirement[] | null;
  highlight: { id: string; page: number; found: boolean }[] | null;
  comparison: Comparison | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

const post = (body?: unknown): RequestInit =>
  body instanceof FormData
    ? { method: "POST", body }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) };

const form = (file: File) => {
  const data = new FormData();
  data.append("file", file);
  return data;
};

export const api = {
  listDocuments: () => request<Doc[]>("/documents"),
  upload: (file: File) => request<Doc & { pages: number; chunks: number }>("/documents", post(form(file))),
  remove: (docId: string) => request(`/documents/${docId}`, { method: "DELETE" }),
  ask: (question: string, docId?: string) => request<Answer>("/ask", post({ question, doc_id: docId || null })),
  state: (docId: string) => request<DocState>(`/documents/${docId}/state`),
  insights: (docId: string) => request<Insights>(`/documents/${docId}/insights`, post()),
  requirements: (docId: string) => request(`/documents/${docId}/requirements`, post()),
  review: (docId: string) => request(`/documents/${docId}/review`, post()),
  highlight: (docId: string) => request(`/documents/${docId}/highlight`, post()),
  pipeline: (docId: string) => request<DocState>(`/documents/${docId}/pipeline`, post()),
  groundTruth: (docId: string, file: File) => request<Comparison>(`/documents/${docId}/ground-truth`, post(form(file))),
  fileUrl: (docId: string, name: string) => `/api/documents/${docId}/files/${name}`,
};
