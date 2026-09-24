import { create } from "zustand";
import { EvolutionSummary, GraphEdgeData, GraphNodeData, NodeType, Session, SessionLog, Task } from "../types";
import { api } from "../services/api";
import {
  MOCK_EVOLUTION_SUMMARY,
  MOCK_GRAPH_DATA,
  MOCK_SESSION_LOGS,
  MOCK_SESSIONS,
  MOCK_TASKS,
} from "./mockData";

export interface ToastItem {
  id: string;
  type: "success" | "error" | "info" | "warning";
  message: string;
}

interface StudioState {
  // Navigation & General UI
  activeTab: "tasks" | "launcher" | "graph" | "evolution";
  isLiveConnected: boolean;
  isLoading: boolean;
  toasts: ToastItem[];

  // Tasks state
  tasks: Task[];
  selectedTaskId: string | null;

  // Sessions state
  sessions: Session[];
  selectedSessionId: string | null;
  sessionViewMode: "grid" | "table";

  // Graph state
  graphNodes: GraphNodeData[];
  graphEdges: GraphEdgeData[];
  selectedNode: GraphNodeData | null;
  isInspectorOpen: boolean;
  filterNodeType: NodeType | "ALL";
  searchQuery: string;

  // Evolution state
  evolutionSummary: EvolutionSummary | null;
  sessionLogs: SessionLog[];

  // Actions
  setActiveTab: (tab: "tasks" | "launcher" | "graph" | "evolution") => void;
  setSessionViewMode: (mode: "grid" | "table") => void;
  addToast: (message: string, type?: "success" | "error" | "info" | "warning") => void;
  removeToast: (id: string) => void;

  // Selection
  setSelectedTaskId: (taskId: string | null) => void;
  setSelectedSessionId: (sessionId: string | null) => void;
  setSelectedNode: (node: GraphNodeData | null) => void;
  setIsInspectorOpen: (open: boolean) => void;
  setFilterNodeType: (type: NodeType | "ALL") => void;
  setSearchQuery: (query: string) => void;

  // Data fetching & operations
  fetchTasks: () => Promise<void>;
  createTask: (data: {
    name: string;
    goal_description: string;
    instructions: string;
    env_vars?: Record<string, any>;
    initial_urls?: string[];
    browser_config?: Record<string, any>;
  }) => Promise<Task | null>;

  fetchSessions: (taskId?: string) => Promise<void>;
  launchSession: (sessionId: string) => Promise<boolean>;
  closeSession: (sessionId: string) => Promise<boolean>;

  fetchGraph: (sessionId: string) => Promise<void>;
  updateNodeAlias: (sessionId: string, nodeId: string, alias: string) => Promise<boolean>;
  deleteNode: (sessionId: string, nodeId: string) => Promise<boolean>;

  fetchEvolution: (taskId?: string) => Promise<void>;
}

export const useStudioStore = create<StudioState>((set, get) => ({
  activeTab: "tasks",
  isLiveConnected: false,
  isLoading: false,
  toasts: [],

  tasks: MOCK_TASKS,
  selectedTaskId: MOCK_TASKS[0]?.id || null,

  sessions: MOCK_SESSIONS[MOCK_TASKS[0]?.id] || [],
  selectedSessionId: MOCK_SESSIONS[MOCK_TASKS[0]?.id]?.[0]?.id || null,
  sessionViewMode: "grid",

  graphNodes: MOCK_GRAPH_DATA["sess_shopee_item_01"]?.nodes || [],
  graphEdges: MOCK_GRAPH_DATA["sess_shopee_item_01"]?.edges || [],
  selectedNode: null,
  isInspectorOpen: false,
  filterNodeType: "ALL",
  searchQuery: "",

  evolutionSummary: MOCK_EVOLUTION_SUMMARY,
  sessionLogs: MOCK_SESSION_LOGS,

  setActiveTab: (tab) => set({ activeTab: tab }),
  setSessionViewMode: (mode) => set({ sessionViewMode: mode }),

  addToast: (message, type = "info") => {
    const id = Math.random().toString(36).substring(2, 9);
    set((state) => ({
      toasts: [...state.toasts, { id, message, type }],
    }));
    setTimeout(() => {
      get().removeToast(id);
    }, 4500);
  },

  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },

  setSelectedTaskId: (taskId) => {
    set({ selectedTaskId: taskId });
    if (taskId) {
      get().fetchSessions(taskId);
      get().fetchEvolution(taskId);
    }
  },

  setSelectedSessionId: (sessionId) => {
    set({ selectedSessionId: sessionId });
    if (sessionId) {
      get().fetchGraph(sessionId);
    }
  },

  setSelectedNode: (node) => {
    set({ selectedNode: node, isInspectorOpen: !!node });
  },

  setIsInspectorOpen: (open) => set({ isInspectorOpen: open }),
  setFilterNodeType: (type) => set({ filterNodeType: type }),
  setSearchQuery: (query) => set({ searchQuery: query }),

  // 1. Tasks
  fetchTasks: async () => {
    set({ isLoading: true });
    try {
      const data = await api.listTasks();
      if (data && data.tasks && data.tasks.length > 0) {
        set({ tasks: data.tasks, isLiveConnected: true });
        const curTask = get().selectedTaskId;
        if (!curTask || !data.tasks.find((t) => t.id === curTask)) {
          set({ selectedTaskId: data.tasks[0].id });
          get().fetchSessions(data.tasks[0].id);
        }
      }
    } catch {
      // Backend not running yet: retain Mock Data gracefully
      set({ isLiveConnected: false });
    } finally {
      set({ isLoading: false });
    }
  },

  createTask: async (input) => {
    set({ isLoading: true });
    try {
      const newTask = await api.createTask(input);
      set((state) => ({
        tasks: [newTask, ...state.tasks],
        selectedTaskId: newTask.id,
        isLiveConnected: true,
      }));
      get().addToast(`Task "${newTask.name}" created successfully!`, "success");
      get().fetchSessions(newTask.id);
      return newTask;
    } catch {
      // Offline fallback: generate mock task locally
      const mockId = `task_${Date.now().toString(36)}`;
      const urls = input.initial_urls || [];
      const generatedSessionIds = urls.map((_, idx) => `sess_${mockId}_${idx + 1}`);

      const fallbackTask: Task = {
        id: mockId,
        name: input.name,
        goal_description: input.goal_description,
        instructions: input.instructions,
        env_vars: input.env_vars || {},
        initial_urls: urls,
        browser_config: {
          headless: input.browser_config?.headless ?? false,
          use_cloakbrowser: input.browser_config?.use_cloakbrowser ?? true,
          user_agent: input.browser_config?.user_agent,
          viewport_width: input.browser_config?.viewport_width ?? 1440,
          viewport_height: input.browser_config?.viewport_height ?? 900,
        },
        status: "CREATED",
        session_ids: generatedSessionIds,
        created_at_ns: Date.now() * 1_000_000,
        updated_at_ns: Date.now() * 1_000_000,
        metadata: { author: "PlaygroundUser" },
      };

      const fallbackSessions: Session[] = urls.map((url, idx) => ({
        id: generatedSessionIds[idx],
        task_id: mockId,
        source: "browser_agent",
        name: `Session ${idx + 1}: ${new URL(url).pathname || url}`,
        target: url,
        status: "CREATED",
        started_at_ns: Date.now() * 1_000_000,
        event_count: 0,
      }));

      MOCK_SESSIONS[mockId] = fallbackSessions;

      set((state) => ({
        tasks: [fallbackTask, ...state.tasks],
        selectedTaskId: mockId,
        sessions: fallbackSessions,
        selectedSessionId: fallbackSessions[0]?.id || null,
        activeTab: "launcher",
      }));

      get().addToast(`Task "${fallbackTask.name}" created with ${urls.length} sessions!`, "success");
      return fallbackTask;
    } finally {
      set({ isLoading: false });
    }
  },

  // 2. Sessions
  fetchSessions: async (taskId) => {
    const targetId = taskId || get().selectedTaskId;
    if (!targetId) return;

    try {
      const data = await api.listSessions(targetId);
      if (Array.isArray(data) && data.length > 0) {
        set({ sessions: data, isLiveConnected: true });
        if (!get().selectedSessionId || !data.find((s) => s.id === get().selectedSessionId)) {
          set({ selectedSessionId: data[0].id });
          get().fetchGraph(data[0].id);
        }
        return;
      }
    } catch {
      set({ isLiveConnected: false });
    }

    // Fallback to mock sessions
    const mockList = MOCK_SESSIONS[targetId] || [];
    set({
      sessions: mockList,
      selectedSessionId: mockList[0]?.id || null,
    });
    if (mockList[0]?.id) {
      get().fetchGraph(mockList[0].id);
    }
  },

  launchSession: async (sessionId) => {
    get().addToast(`Launching browser for session ${sessionId}...`, "info");
    try {
      await api.launchSession(sessionId);
      get().addToast(`Browser launched! Capturing hooks active.`, "success");
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, status: "RUNNING", event_count: (s.event_count || 0) + 12 } : s
        ),
      }));
      return true;
    } catch {
      // Mock simulation: mark as RUNNING
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, status: "RUNNING", event_count: (s.event_count || 0) + 48 } : s
        ),
      }));
      get().addToast(`[Demo] Browser session ${sessionId} started and capturing network & DOM events!`, "success");
      return true;
    }
  },

  closeSession: async (sessionId) => {
    get().addToast(`Closing session ${sessionId} & projecting lineage graph...`, "info");
    try {
      const res = await api.closeSession(sessionId);
      get().addToast(`Session closed! ${res.event_count || 120} events projected to graph.`, "success");
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, status: "COMPLETED", event_count: res.event_count || s.event_count } : s
        ),
      }));
      get().fetchGraph(sessionId);
      return true;
    } catch {
      // Mock simulation: mark as COMPLETED
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, status: "COMPLETED", event_count: (s.event_count || 150) + 75 } : s
        ),
      }));
      get().addToast(`[Demo] Session closed! Lineage Graph projected. Click "View Graph" to explore.`, "success");
      get().fetchGraph(sessionId);
      return true;
    }
  },

  // 3. Graph
  fetchGraph: async (sessionId) => {
    if (!sessionId) return;
    try {
      const data = await api.getGraph(sessionId);
      if (data && data.nodes && data.nodes.length > 0) {
        set({ graphNodes: data.nodes, graphEdges: data.edges || [] });
        return;
      }
    } catch {
      // fallback
    }

    const mockGraph = MOCK_GRAPH_DATA[sessionId] || MOCK_GRAPH_DATA["sess_shopee_item_01"] || { nodes: [], edges: [] };
    set({
      graphNodes: mockGraph.nodes,
      graphEdges: mockGraph.edges,
      selectedNode: null,
      isInspectorOpen: false,
    });
  },

  updateNodeAlias: async (sessionId, nodeId, alias) => {
    try {
      await api.updateNodeAlias(sessionId, nodeId, alias);
    } catch {
      // proceed in state
    }

    set((state) => {
      const updatedNodes = state.graphNodes.map((n) => (n.id === nodeId ? { ...n, alias } : n));
      const updatedSelected = state.selectedNode?.id === nodeId ? { ...state.selectedNode, alias } : state.selectedNode;
      return { graphNodes: updatedNodes, selectedNode: updatedSelected };
    });

    get().addToast(`Updated node alias to "${alias}"`, "success");
    return true;
  },

  deleteNode: async (sessionId, nodeId) => {
    try {
      await api.deleteNode(sessionId, nodeId);
    } catch {
      // proceed in state
    }

    set((state) => {
      const updatedNodes = state.graphNodes.filter((n) => n.id !== nodeId);
      const updatedEdges = state.graphEdges.filter((e) => e.source_id !== nodeId && e.target_id !== nodeId);
      return {
        graphNodes: updatedNodes,
        graphEdges: updatedEdges,
        selectedNode: null,
        isInspectorOpen: false,
      };
    });

    get().addToast(`Deleted node ${nodeId} and related edges.`, "warning");
    return true;
  },

  // 4. Evolution
  fetchEvolution: async (taskId) => {
    const targetId = taskId || get().selectedTaskId;
    try {
      const summary = await api.getEvolutionSummary(targetId || undefined);
      if (summary) set({ evolutionSummary: summary });
      if (targetId) {
        const logs = await api.getSessionLogs(targetId);
        if (logs) set({ sessionLogs: logs });
      }
    } catch {
      set({
        evolutionSummary: MOCK_EVOLUTION_SUMMARY,
        sessionLogs: MOCK_SESSION_LOGS,
      });
    }
  },
}));
