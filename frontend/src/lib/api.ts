import { BusinessProfile, FullReasoningReport, GovernmentScheme } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export async function fetchSampleProfile(sampleId: number): Promise<BusinessProfile> {
  const res = await fetch(`${API_BASE}/api/sample-profile/${sampleId}`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to load sample profile ${sampleId}`);
  return res.json();
}

export async function uploadDocument(file: File): Promise<{ profile: BusinessProfile; file_name: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload-document`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Document upload and extraction failed");
  return res.json();
}

export async function deliberateSchemes(
  profile: BusinessProfile,
  query?: string,
  topK: number = 4
): Promise<FullReasoningReport> {
  const res = await fetch(`${API_BASE}/api/schemes/deliberate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile, query, top_k: topK, apply_hard_filters: true }),
  });
  if (!res.ok) throw new Error("Failed to deliberate schemes");
  return res.json();
}

export async function fetchAllSchemes(): Promise<GovernmentScheme[]> {
  const res = await fetch(`${API_BASE}/api/schemes?limit=50`);
  if (!res.ok) throw new Error("Failed to fetch schemes list");
  const data = await res.json();
  return data.schemes || [];
}

export async function sendChatMessage(
  message: string,
  profile?: BusinessProfile | null
): Promise<{ reply: string; cited_schemes: any[]; suggested_actions: string[] }> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, profile }),
  });
  if (!res.ok) throw new Error("Chat copilot query failed");
  return res.json();
}
