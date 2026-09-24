export type TaskStatus = "CREATED" | "IN_PROGRESS" | "COMPLETED" | "FAILED";
export type SessionStatus = "CREATED" | "RUNNING" | "STOPPED" | "FAILED" | "COMPLETED";

export interface BrowserConfig {
  headless: boolean;
  use_cloakbrowser: boolean;
  user_agent?: string;
  custom_headers?: Record<string, string>;
  pre_seed_storage?: Record<string, any>;
  proxy?: string;
  viewport_width?: number;
  viewport_height?: number;
}

export interface Task {
  id: string;
  name: string;
  goal_description: string;
  instructions: string;
  env_vars: Record<string, any>;
  initial_urls: string[];
  browser_config: BrowserConfig;
  status: TaskStatus;
  session_ids: string[];
  created_at_ns: number;
  updated_at_ns: number;
  metadata: Record<string, any>;
}

export interface Session {
  id: string;
  task_id?: string;
  source: string;
  name: string;
  target?: string;
  status: string;
  started_at_ns: number;
  ended_at_ns?: number;
  event_count?: number;
  metadata?: Record<string, any>;
}

export type NodeType = "REQUEST" | "FUNCTION" | "CRYPTO" | "STORAGE" | "VALUE";

export interface GraphNodeData {
  id: string;
  session_id: string;
  node_type: NodeType;
  label?: string;
  alias?: string;
  entity_id?: string;
  properties: Record<string, any>;
  created_at_ns: number;
}

export interface GraphEdgeData {
  id: number | string;
  session_id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  confidence: number;
  provenance_status: string;
  properties: Record<string, any>;
}

export interface ToolProposal {
  name: string;
  purpose: string;
  parameters?: Record<string, any>;
  expected_output?: string;
  task_id?: string;
  created_at_ns?: number;
}

export interface SessionLog {
  id: string;
  task_id: string;
  session_id?: string;
  log_type: string;
  agent_evaluation: string;
  missing_tools: string[];
  suggested_tools: ToolProposal[];
  bottlenecks: string[];
  efficiency_rating: number;
  created_at_ns: number;
  metadata?: Record<string, any>;
}

export interface EvolutionSummary {
  total_retrospectives: number;
  average_efficiency_rating: number;
  top_missing_tools: Array<{ tool: string; frequency: number }>;
  recent_proposals: ToolProposal[];
  common_bottlenecks: Array<{ bottleneck: string; frequency: number }>;
}
