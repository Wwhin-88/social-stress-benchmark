
export interface ScenarioItem {
  id: string;
  name: string;
  archetype: string;
}

export interface ScenariosResponse {
  scenarios: ScenarioItem[];
}

export interface RunRequest {
  provider: string;
  model: string;
  api_key: string;
  api_base?: string;
  max_tokens?: number | null;
  temperature?: number | null;
  reviewer_provider: string;
  reviewer_model: string;
  reviewer_api_key: string;
  reviewer_api_base?: string;
  scenarios: string[];
  subtests?: string[] | null;
  defender_variant: string;
}

export interface RunResponse {
  run_id: string;
  status: string;
}

export interface RunItem {
  run_id: string;
  model: string;
  scenario: string;
  defender: string;
  composite_score: number;
  gate_passed: number; // 0 или 1
  status: string;
  timestamp: string;
  result_json: string; // JSON-строка!
}

export interface RunsResponse {
  runs: RunItem[];
}

export async function fetchScenarios(): Promise<ScenariosResponse> {
  const res = await fetch(`/api/v1/scenarios`);
  if (!res.ok) throw new Error(`Scenarios fetch failed: ${res.status}`);
  return res.json();
}

export async function startRun(req: RunRequest): Promise<RunResponse> {
  const res = await fetch(`/api/v1/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Run start failed: ${res.status}`);
  return res.json();
}

export async function fetchRuns(limit = 50): Promise<RunsResponse> {
  const res = await fetch(`/api/v1/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`Runs fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchRun(runId: string): Promise<RunItem> {
  const res = await fetch(`/api/v1/run/${runId}`);
  if (!res.ok) throw new Error(`Run fetch failed: ${res.status}`);
  return res.json();
}

export function createRunStream(runId: string): EventSource {
  return new EventSource(`/api/v1/run/${runId}/stream`);
}
