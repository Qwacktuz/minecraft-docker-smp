// Types for minecraft.js, for the web app's TypeScript (web/). The Worker ignores this file.
export interface GitHubEnv {
  REPO: string;
  WORKFLOW: string;
  GITHUB_TOKEN: string;
}

export interface WorkflowRun {
  id: number;
  status: string;
  conclusion: string | null;
  event: string;
  display_title: string;
  html_url: string;
  created_at: string;
  updated_at: string;
  run_started_at?: string;
  actor?: { login: string };
  triggering_actor?: { login: string };
}

export function vpsAddress(host: string): Promise<string | null>;
import type { ServerStatus } from './logic.js';

export function serverStatus(address: string, host: string, port: number): Promise<ServerStatus | null>;
export function playersOnline(address: string, host: string, port: number): Promise<number | null>;
export function github(env: GitHubEnv, path: string, init?: RequestInit): Promise<Response>;
export function recentRuns(env: GitHubEnv, count?: number): Promise<WorkflowRun[]>;
export function runsInFlight(env: GitHubEnv): Promise<number>;
export function dispatch(env: GitHubEnv, action: 'start' | 'stop'): Promise<void>;
