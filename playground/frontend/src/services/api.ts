import { EvolutionSummary, GraphEdgeData, GraphNodeData, Session, SessionLog, Task } from "../types";

const API_BASE = "/api";

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
      ...options,
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed with status ${res.status}`);
    }

    return await res.json();
  } catch (err: any) {
    console.warn(`[API] Endpoint ${endpoint} failed:`, err.message);
    throw err;
  }
}

export const api = {
  // 1. Task APIs
  async createTask(input: {
    name: string;
    goal_description: string;
    instructions: string;
    env_vars?: Record<string, any>;
    initial_urls?: string[];
    browser_config?: Record<string, any>;
    task_id?: string;
  }): Promise<Task> {
    return request<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  async listTasks(status?: string): Promise<{ tasks: Task[]; count: number }> {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<{ tasks: Task[]; count: number }>(`/tasks${query}`);
  },

  async getTask(taskId: string): Promise<Task> {
    return request<Task>(`/tasks/${taskId}`);
  },

  async updateTaskStatus(taskId: string, status: string, notes?: string): Promise<{ success: boolean }> {
    return request<{ success: boolean }>(`/tasks/${taskId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status, notes }),
    });
  },

  // 2. Session APIs
  async listSessions(taskId?: string): Promise<Session[]> {
    const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    return request<Session[]>(`/sessions${query}`);
  },

  async launchSession(sessionId: string): Promise<{ success: boolean; browser_pid?: number }> {
    return request<{ success: boolean; browser_pid?: number }>(`/sessions/${sessionId}/launch`, {
      method: "POST",
    });
  },

  async closeSession(sessionId: string): Promise<{ success: boolean; event_count: number; graph_projected: boolean }> {
    return request<{ success: boolean; event_count: number; graph_projected: boolean }>(`/sessions/${sessionId}/close`, {
      method: "POST",
    });
  },

  async getSessionStatus(sessionId: string): Promise<Record<string, any>> {
    return request<Record<string, any>>(`/sessions/${sessionId}/status`);
  },

  // 3. Graph APIs
  async getGraph(sessionId: string): Promise<{ nodes: GraphNodeData[]; edges: GraphEdgeData[] }> {
    return request<{ nodes: GraphNodeData[]; edges: GraphEdgeData[] }>(`/graph/${sessionId}`);
  },

  async updateNodeAlias(sessionId: string, nodeId: string, alias: string): Promise<{ success: boolean }> {
    return request<{ success: boolean }>(`/graph/${sessionId}/nodes/${nodeId}/alias`, {
      method: "PATCH",
      body: JSON.stringify({ alias }),
    });
  },

  async deleteNode(sessionId: string, nodeId: string): Promise<{ success: boolean; deleted_edges: number }> {
    return request<{ success: boolean; deleted_edges: number }>(`/graph/${sessionId}/nodes/${nodeId}`, {
      method: "DELETE",
    });
  },

  // 4. Evolution / Retrospective APIs
  async getSessionLogs(taskId: string): Promise<SessionLog[]> {
    return request<SessionLog[]>(`/evolution/logs/${taskId}`);
  },

  async getEvolutionSummary(taskId?: string): Promise<EvolutionSummary> {
    const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    return request<EvolutionSummary>(`/evolution/summary${query}`);
  },
};
