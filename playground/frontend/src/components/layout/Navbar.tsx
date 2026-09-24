import React from "react";
import {
  Layers,
  Play,
  Share2,
  Sparkles,
  RefreshCw,
  Cpu,
  ChevronRight,
  Radio,
} from "lucide-react";
import { useStudioStore } from "../../stores/useStudioStore";

export const Navbar: React.FC = () => {
  const {
    activeTab,
    setActiveTab,
    tasks,
    selectedTaskId,
    setSelectedTaskId,
    sessions,
    graphNodes,
    isLiveConnected,
    fetchTasks,
    isLoading,
  } = useStudioStore();

  const currentTask = tasks.find((t) => t.id === selectedTaskId);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border-subtle bg-background-surface/80 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between px-4 sm:px-6">
        {/* Brand & Task Breadcrumb */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 font-semibold text-slate-100">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600/20 border border-indigo-500/40 text-indigo-400">
              <Cpu className="h-4 w-4" />
            </div>
            <span className="tracking-tight text-sm font-bold bg-gradient-to-r from-indigo-300 via-slate-100 to-indigo-100 bg-clip-text text-transparent">
              MCP Reverse Studio
            </span>
          </div>

          <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-500 pl-2">
            <ChevronRight className="h-3.5 w-3.5" />
            <span className="text-slate-400">Task:</span>
            <select
              value={selectedTaskId || ""}
              onChange={(e) => setSelectedTaskId(e.target.value)}
              className="bg-background-elevated border border-border-subtle text-slate-200 rounded px-2 py-0.5 text-xs focus:outline-none focus:border-indigo-500"
            >
              {tasks.map((task) => (
                <option key={task.id} value={task.id}>
                  {task.name} ({task.status})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 bg-background-base/60 p-1 rounded-lg border border-border-subtle">
          <button
            onClick={() => setActiveTab("tasks")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === "tasks"
                ? "bg-indigo-600 text-white shadow-glow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            <span>Task Config</span>
          </button>

          <button
            onClick={() => setActiveTab("launcher")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === "launcher"
                ? "bg-indigo-600 text-white shadow-glow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Play className="h-3.5 w-3.5" />
            <span>Sessions</span>
            <span className="ml-0.5 rounded-full bg-slate-800 px-1.5 py-0.2 text-[10px] text-slate-300">
              {sessions.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("graph")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === "graph"
                ? "bg-indigo-600 text-white shadow-glow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Share2 className="h-3.5 w-3.5" />
            <span>Graph Studio</span>
            <span className="ml-0.5 rounded-full bg-slate-800 px-1.5 py-0.2 text-[10px] text-slate-300">
              {graphNodes.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("evolution")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === "evolution"
                ? "bg-indigo-600 text-white shadow-glow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Sparkles className="h-3.5 w-3.5 text-amber-400" />
            <span>Evolution</span>
          </button>
        </nav>

        {/* Right Status & Refresh */}
        <div className="flex items-center gap-3">
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border-subtle bg-background-elevated text-[11px]"
            title={isLiveConnected ? "Connected to Starlette API Backend" : "Demo Mode with Mock Data Fallback"}
          >
            <span className="relative flex h-2 w-2">
              {isLiveConnected && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              )}
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  isLiveConnected ? "bg-emerald-500" : "bg-amber-400"
                }`}
              ></span>
            </span>
            <span className={isLiveConnected ? "text-emerald-300" : "text-amber-300"}>
              {isLiveConnected ? "API Live" : "Demo Mock"}
            </span>
          </div>

          <button
            onClick={() => fetchTasks()}
            disabled={isLoading}
            className="p-1.5 rounded-md border border-border-subtle text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            title="Refresh Data from Backend"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>
    </header>
  );
};
