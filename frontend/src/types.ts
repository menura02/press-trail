export type SourceInput = {
  name: string; url: string; language: "tr"; active: boolean;
  full_text: boolean; interval_minutes: number;
};
export type Source = SourceInput & { id: number; demo: boolean; next_check: string };
export type Run = {
  id: number; source_id: number; status: string; created_at: string; started_at: string | null;
  finished_at: string | null; attempts: number; seen: number; versions: number; skipped: number; error: string | null;
};
export type Version = {
  id: number; title: string; summary: string; body?: string; scope: "full" | "feed"; extractor: string;
  published: string | null; published_raw: string | null; published_state: string;
  updated: string | null; updated_raw: string | null; updated_state: string; collected_at: string;
};
export type Membership = {
  cluster_id: number | null; decision: string; method: string; score: number | null;
};
export type Article = {
  id: number; source: Source; url: string; first_seen: string;
  version: Version; membership: Membership | null;
};
export type EvidenceLink = {
  id: number; version_id: number; url: string; text: string; context: string;
  kind: "explicit" | "link"; target_ids: number[];
};
export type ArticleDetail = Article & { versions: Version[]; links: EvidenceLink[] };
export type Group = { id: number; title: string; count: number; demo: boolean };
export type GroupList = { items: Group[]; more: boolean };
export type GroupDetail = Pick<Group, "id" | "title"> & { articles: Article[]; links: EvidenceLink[] };
export type Comparison = {
  left: Version; right: Version; score: number | null; method: string; analysis_version: string;
  threshold: number; segments: { left: string; right: string }[];
};

