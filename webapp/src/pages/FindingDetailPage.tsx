import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Download, FileText, MessageSquare, Paperclip, Send, Upload,
} from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { SeverityBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { PageHeader, SectionCard } from "@/components/ui/page";
import { api, getToken, type Finding } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface Comment {
  id: string;
  finding_id: string;
  author_id?: string;
  body: string;
  is_review_signoff: boolean;
  created_at?: string;
}

interface Attachment {
  id: string;
  filename: string;
  content_type?: string;
  sha256: string;
  bytes: number;
  uploaded_at?: string;
  uploaded_by?: string;
}

const NEXT_STATES: Record<string, string[]> = {
  DRAFT: ["UNDER_REVIEW", "FALSE_POSITIVE"],
  UNDER_REVIEW: ["CONFIRMED", "FALSE_POSITIVE", "DRAFT"],
  CONFIRMED: ["REMEDIATED", "ACCEPTED_RISK", "CARRIED_FORWARD"],
  FALSE_POSITIVE: ["DRAFT"],
  CARRIED_FORWARD: ["CONFIRMED", "REMEDIATED"],
};

export function FindingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: finding, isLoading } = useQuery({
    queryKey: ["finding", id],
    queryFn: () => api.get<Finding>(`/api/findings/${id}`),
    enabled: !!id,
  });

  const { data: comments = [] } = useQuery({
    queryKey: ["finding-comments", id],
    queryFn: () => api.get<Comment[]>(`/api/findings/${id}/comments`),
    enabled: !!id,
  });

  const { data: attachments = [] } = useQuery({
    queryKey: ["finding-attachments", id],
    queryFn: () => api.get<Attachment[]>(`/api/findings/${id}/attachments`),
    enabled: !!id,
  });

  const [newComment, setNewComment] = useState("");
  const [transitionComment, setTransitionComment] = useState("");

  const transition = useMutation({
    mutationFn: (status: string) =>
      api.post(`/api/findings/${id}/transition`, {
        status,
        comment: transitionComment || null,
      }),
    onSuccess: (_, status) => {
      toast({ kind: "success", title: `Transitioned to ${status.replace(/_/g, " ")}` });
      setTransitionComment("");
      qc.invalidateQueries({ queryKey: ["finding", id] });
      qc.invalidateQueries({ queryKey: ["finding-comments", id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
    },
    onError: (e) => toast({ kind: "error", title: "Transition failed", description: (e as Error).message }),
  });

  const addComment = useMutation({
    mutationFn: () => api.post(`/api/findings/${id}/comments`, { body: newComment }),
    onSuccess: () => {
      setNewComment("");
      qc.invalidateQueries({ queryKey: ["finding-comments", id] });
      toast({ kind: "success", title: "Comment posted" });
    },
  });

  const uploadAttachment = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.post(`/api/findings/${id}/attachments`, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finding-attachments", id] });
      toast({ kind: "success", title: "Attachment uploaded" });
    },
    onError: (e) => toast({ kind: "error", title: "Upload failed", description: (e as Error).message }),
  });

  if (isLoading || !finding) return null;
  const allowed = NEXT_STATES[finding.status] || [];

  return (
    <>
      <button
        onClick={() => navigate("/findings")}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3"
      >
        <ArrowLeft className="h-4 w-4" /> Back to findings
      </button>
      <PageHeader
        title={finding.code}
        description={finding.title}
        actions={
          <div className="flex items-center gap-2">
            <SeverityBadge severity={finding.severity} />
            <StatusBadge status={finding.status} />
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <SectionCard title="Description">
            {finding.description ? (
              <div className="text-sm whitespace-pre-wrap leading-relaxed">{finding.description}</div>
            ) : (
              <div className="text-sm text-muted-foreground italic">No description.</div>
            )}
          </SectionCard>

          <SectionCard title={`Comments (${comments.length})`}>
            {comments.length === 0 ? (
              <div className="text-sm text-muted-foreground italic">No comments yet.</div>
            ) : (
              <div className="space-y-3 mb-4">
                {comments.map((c) => (
                  <div key={c.id} className={`rounded-md border p-3 ${
                    c.is_review_signoff ? "border-success/30 bg-success/5" : ""
                  }`}>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {c.is_review_signoff && (
                        <span className="text-success font-semibold">✓ Review sign-off</span>
                      )}
                      <span>{c.created_at ? new Date(c.created_at).toLocaleString() : "—"}</span>
                    </div>
                    <div className="text-sm mt-1.5 whitespace-pre-wrap">{c.body}</div>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Textarea
                placeholder="Add a comment…"
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                rows={2}
                className="flex-1"
              />
              <Button
                onClick={() => addComment.mutate()}
                disabled={!newComment.trim() || addComment.isPending}
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </SectionCard>

          <SectionCard
            title={`Attachments (${attachments.length})`}
            actions={
              <>
                <input
                  ref={fileRef} type="file" className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadAttachment.mutate(f);
                    if (fileRef.current) fileRef.current.value = "";
                  }}
                />
                <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}
                        disabled={uploadAttachment.isPending}>
                  <Upload className="h-4 w-4" /> Upload
                </Button>
              </>
            }
          >
            {attachments.length === 0 ? (
              <div className="text-sm text-muted-foreground italic">
                Attach evidence — screenshots, emails, PDFs.
              </div>
            ) : (
              <div className="divide-y">
                {attachments.map((a) => (
                  <div key={a.id} className="flex items-center gap-3 py-2">
                    <Paperclip className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{a.filename}</div>
                      <div className="text-[11px] text-muted-foreground">
                        {(a.bytes / 1024).toFixed(1)} KB · sha256 {a.sha256.slice(0, 12)}…
                      </div>
                    </div>
                    <button
                      className="text-xs text-accent hover:underline flex items-center gap-1"
                      onClick={async () => {
                        const r = await fetch(
                          `/api/findings/${id}/attachments/${a.id}`,
                          { headers: { Authorization: `Bearer ${getToken()}` } },
                        );
                        const blob = await r.blob();
                        const u = URL.createObjectURL(blob);
                        const link = document.createElement("a");
                        link.href = u; link.download = a.filename; link.click();
                      }}
                    >
                      <Download className="h-3 w-3" /> Download
                    </button>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          <SectionCard title="Details">
            <dl className="space-y-2 text-sm">
              <Row label="Risk score" value={finding.risk_score?.toFixed(1) ?? "—"} />
              <Row label="Due date" value={finding.due_date ?? "—"} />
              <Row label="Created" value={finding.created_at?.slice(0, 16).replace("T", " ") ?? "—"} />
              <Row label="Reviewed" value={finding.reviewed_at?.slice(0, 16).replace("T", " ") ?? "—"} />
              <Row label="Closed" value={finding.closed_at?.slice(0, 16).replace("T", " ") ?? "—"} />
            </dl>
          </SectionCard>

          {finding.record_keys.length > 0 && (
            <SectionCard title={`Records (${finding.record_keys.length})`}>
              <div className="space-y-1 text-xs font-mono">
                {finding.record_keys.slice(0, 20).map((k) => {
                  const target = finding.dataset_id
                    ? `/risk?record=${encodeURIComponent(k)}`
                    : null;
                  return target ? (
                    <Link
                      key={k}
                      to={target}
                      className="block px-2 py-1 rounded bg-secondary hover:bg-secondary/70 truncate"
                      title="Open in Risk Explorer"
                    >
                      {k}
                    </Link>
                  ) : (
                    <div
                      key={k}
                      className="block px-2 py-1 rounded bg-secondary truncate"
                    >
                      {k}
                    </div>
                  );
                })}
                {finding.record_keys.length > 20 && (
                  <div className="text-[11px] text-muted-foreground px-2 pt-1">
                    +{finding.record_keys.length - 20} more…
                  </div>
                )}
              </div>
            </SectionCard>
          )}

          {finding.linked_template_codes.length > 0 && (
            <SectionCard title="Linked templates">
              <div className="flex flex-wrap gap-1.5">
                {finding.linked_template_codes.map((c) => (
                  <Link
                    key={c} to={`/templates?code=${encodeURIComponent(c)}`}
                    className="inline-flex items-center px-2 py-0.5 rounded-md bg-accent/10 text-accent text-xs font-mono hover:bg-accent/20"
                  >
                    {c}
                  </Link>
                ))}
              </div>
            </SectionCard>
          )}

          {allowed.length > 0 && (
            <SectionCard title="Workflow">
              <Textarea
                placeholder="Comment / sign-off note (optional)"
                value={transitionComment}
                onChange={(e) => setTransitionComment(e.target.value)}
                rows={2}
                className="mb-3"
              />
              <div className="flex flex-wrap gap-1.5">
                {allowed.map((s) => (
                  <Button
                    key={s} variant="outline" size="sm"
                    onClick={() => transition.mutate(s)}
                    disabled={transition.isPending}
                  >
                    → {s.replace(/_/g, " ")}
                  </Button>
                ))}
              </div>
              <div className="text-[11px] text-muted-foreground mt-3">
                CONFIRMED / FALSE_POSITIVE / REMEDIATED require a reviewer ≠ the finding owner.
              </div>
            </SectionCard>
          )}
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
