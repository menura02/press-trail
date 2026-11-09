import type { Version } from "./types";

export type Page<T> = { items: T[]; more: boolean };
export type Review = "pending" | "confirmed" | "rejected";
export type Field = "title" | "summary" | "body";
export type NoteKind = "article" | "version" | "diff" | "finding";
export type WatchKind = "article" | "cluster";
export type NoteStatus = "open" | "reviewed" | "resolved";
export type Note = {
  id: number; text: string; tags: string[]; status: NoteStatus;
  created_at: string; updated_at: string;
};
export type VersionEvidence = Pick<Version, "id" | "title" | "published" | "published_raw" |
  "published_state" | "collected_at" | "scope" | "extractor"> & { article_id: number };
export type Finding = {
  id: number; kind: "claim" | "correction"; field: Field; start: number; end: number;
  quote: string; context: string; method: string; status: Review; source: string; url: string; demo: boolean;
  version: VersionEvidence;
  signals: { numbers: { raw: string; value: string; unit: string | null }[]; dates: string[]; quotes: string[] };
};
export type ClaimPair = {
  id: number; left: Finding; right: Finding; status: Review; method: string; current_group: boolean;
};
export type Changes<T> = { added: T[]; removed: T[] };
export type ParagraphDiff = {
  kind: "added" | "removed" | "changed" | "moved"; before: string; after: string;
  before_index: number | null; after_index: number | null;
  words?: { kind: string; before: string; after: string }[];
  sentences?: Changes<string>; word_limit?: boolean;
};
export type VersionDiff = {
  id: number; article_id: number; before: VersionEvidence; after: VersionEvidence; method: string;
  completed_at: string | null;
  result: {
    fields: Partial<Record<Field, { format_only: boolean; paragraphs: ParagraphDiff[]; truncated: boolean; formatted: number }>>;
    signals: Partial<Record<Field, { numbers: Changes<string>; dates: Changes<string>; quotes: Changes<string> }>>;
    links: Changes<string>; extractor_changed: boolean; scope_changed: boolean; content_changed: boolean;
  } | null;
};
export type DiffOption = { id: number; article_id: number; before_id: number; after_id: number; title: string };
export type Notification = {
  id: number; kind: "group_join" | "version_changed" | "correction"; article_id: number;
  version_id: number; cluster_id: number | null; diff_id: number | null; finding_id: number | null;
  title: string; cluster_title: string | null; created_at: string; read_at: string | null;
};
export type WatchItem = { id: number; target_kind: WatchKind; target_id: number; title: string; created_at: string };

