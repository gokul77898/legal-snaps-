import { JobResponse, JobListItem, HealthStatus } from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function createInfographic(payload: {
  article_name?: string;
  article_url?: string;
  pdf_url?: string;
  language?: string;
  output_format?: string;
  enable_image_generation?: boolean;
  width?: number;
  height?: number;
}): Promise<JobResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/infographics`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to create infographic' }));
    throw new Error(err.detail || 'Failed to submit generation job');
  }

  return resp.json();
}

export async function getInfographic(jobId: string): Promise<JobResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/infographics/${jobId}`, {
    cache: 'no-store',
  });

  if (!resp.ok) {
    throw new Error(`Failed to fetch job status: ${resp.status}`);
  }

  return resp.json();
}

export async function listInfographics(limit: number = 30): Promise<JobListItem[]> {
  const resp = await fetch(`${API_BASE}/api/v1/infographics?limit=${limit}`, {
    cache: 'no-store',
  });

  if (!resp.ok) {
    return [];
  }

  return resp.json();
}

export async function deleteInfographic(jobId: string): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/api/v1/infographics/${jobId}`, {
    method: 'DELETE',
  });
  return resp.status === 204;
}

export async function getHealth(): Promise<HealthStatus | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/health`, { cache: 'no-store' });
    if (resp.ok) return resp.json();
  } catch {
    // Backend offline
  }
  return null;
}

export function getSvgDownloadUrl(jobId: string): string {
  return `${API_BASE}/api/v1/infographics/${jobId}/download/svg`;
}

export function getPngDownloadUrl(jobId: string): string {
  return `${API_BASE}/api/v1/infographics/${jobId}/download/png`;
}

export function getPreviewUrl(jobId: string, format?: string): string {
  return `${API_BASE}/api/v1/infographics/${jobId}/preview${format ? `?format=${format}` : ''}`;
}
