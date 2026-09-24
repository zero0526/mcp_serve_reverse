import React, { useState } from "react";
import {
  Play,
  Square,
  Share2,
  ExternalLink,
  Activity,
  Layers,
  Radio,
  CheckCircle2,
  AlertCircle,
  LayoutGrid,
  List,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import { useStudioStore } from "../../stores/useStudioStore";
import { Session } from "../../types";

export const SessionLauncherGrid: React.FC = () => {
  const {
    tasks,
    selectedTaskId,
    sessions,
    selectedSessionId,
    setSelectedSessionId,
    launchSession,
    closeSession,
    setActiveTab,
    sessionViewMode,
    setSessionViewMode,
    isLoading,
  } = useStudioStore();

  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const currentTask = tasks.find((t) => t.id === selectedTaskId);

  const filteredSessions = sessions.filter((s) => {
    if (statusFilter === "ALL") return true;
    return s.status === statusFilter;
  });

  const handleLaunchAll = async () => {
    for (const session of filteredSessions) {
      if (session.status === "CREATED") {
        await launchSession(session.id);
      }
    }
  };

  const handleCloseAll = async () => {
    for (const session of filteredSessions) {
      if (session.status === "RUNNING") {
        await closeSession(session.id);
      }
    }
  };

  const handleViewGraph = (session: Session) => {
    setSelectedSessionId(session.id);
    setActiveTab("graph");
  };

  if (!currentTask) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-6">
        <Layers className="h-12 w-12 text-slate-600 mb-3" />
        <h3 className="text-base font-semibold text-slate-300">No Task Selected</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Please select a task from the navbar or create a new reverse-engineering task in Task Config.
        </p>
        <button
          onClick={() => setActiveTab("tasks")}
          className="mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium"
        >
          Go to Task Configurator
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Top Header Card */}
      <div className="glass-panel rounded-xl p-5 border border-border-subtle flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-400 border border-indigo-500/30">
              Task
            </span>
            <h2 className="text-base font-bold text-slate-100">{currentTask.name}</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 line-clamp-1">{currentTask.goal_description}</p>
        </div>

        {/* Global Bulk Actions & Controls */}
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-background-base p-1 rounded-lg border border-border-subtle">
            <button
              onClick={() => setSessionViewMode("grid")}
              className={`p-1.5 rounded ${
                sessionViewMode === "grid" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
              title="Grid View"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setSessionViewMode("table")}
              className={`p-1.5 rounded ${
                sessionViewMode === "table" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
              title="Table View"
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            onClick={handleLaunchAll}
            disabled={isLoading || !filteredSessions.some((s) => s.status === "CREATED")}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/20 border border-emerald-500/30 hover:bg-emerald-600/30 text-emerald-300 disabled:opacity-40 rounded-lg text-xs font-medium transition"
          >
            <Play className="w-3 h-3 fill-emerald-400" />
            <span>Launch All Ready</span>
          </button>

          <button
            onClick={handleCloseAll}
            disabled={isLoading || !filteredSessions.some((s) => s.status === "RUNNING")}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600/20 border border-red-500/30 hover:bg-red-600/30 text-red-300 disabled:opacity-40 rounded-lg text-xs font-medium transition"
          >
            <Square className="w-3 h-3 fill-red-400" />
            <span>Close All Running</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-border-subtle pb-3">
        {["ALL", "CREATED", "RUNNING", "COMPLETED", "FAILED"].map((status) => {
          const count =
            status === "ALL" ? sessions.length : sessions.filter((s) => s.status === status).length;
          return (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                statusFilter === status
                  ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
              }`}
            >
              <span>{status}</span>
              <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-400">
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Sessions Grid or Table */}
      {filteredSessions.length === 0 ? (
        <div className="text-center py-16 bg-background-surface/30 rounded-xl border border-dashed border-border-subtle">
          <Activity className="h-10 w-10 text-slate-600 mx-auto mb-2" />
          <p className="text-sm font-medium text-slate-300">No sessions match filter "{statusFilter}"</p>
          <p className="text-xs text-slate-500 mt-1">Configure more start URLs in Task Configurator.</p>
        </div>
      ) : sessionViewMode === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredSessions.map((session) => {
            const isRunning = session.status === "RUNNING";
            const isCompleted = session.status === "COMPLETED";
            const isCreated = session.status === "CREATED";

            return (
              <div
                key={session.id}
                className={`glass-panel rounded-xl p-5 border flex flex-col justify-between transition-all duration-200 hover:border-slate-600 ${
                  isRunning
                    ? "border-emerald-500/50 shadow-glow-green bg-emerald-950/10"
                    : isCompleted
                    ? "border-indigo-500/30"
                    : "border-border-subtle"
                }`}
              >
                <div>
                  {/* Status Indicator Bar */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-2.5 w-2.5">
                        {isRunning && (
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        )}
                        <span
                          className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                            isRunning
                              ? "bg-emerald-400"
                              : isCompleted
                              ? "bg-indigo-400"
                              : "bg-slate-500"
                          }`}
                        />
                      </span>
                      <span
                        className={`text-xs font-bold tracking-wide ${
                          isRunning
                            ? "text-emerald-300"
                            : isCompleted
                            ? "text-indigo-300"
                            : "text-slate-400"
                        }`}
                      >
                        {session.status}
                      </span>
                    </div>

                    <div className="text-[11px] font-mono text-slate-400 bg-background-elevated px-2 py-0.5 rounded border border-border-subtle flex items-center gap-1">
                      <Activity className="w-3 h-3 text-indigo-400" />
                      <span>{session.event_count || 0} events</span>
                    </div>
                  </div>

                  {/* Title & Target URL */}
                  <h4 className="text-sm font-semibold text-slate-100 line-clamp-1">{session.name}</h4>
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mt-2 font-mono break-all bg-background-base/60 p-2 rounded border border-border-subtle">
                    <ExternalLink className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span className="line-clamp-2">{session.target || "about:blank"}</span>
                  </div>
                </div>

                {/* Bottom Actions */}
                <div className="flex items-center justify-between gap-2 mt-5 pt-3 border-t border-border-subtle">
                  <div className="flex items-center gap-2">
                    {isCreated && (
                      <button
                        onClick={() => launchSession(session.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition shadow-sm"
                      >
                        <Play className="w-3 h-3 fill-white" />
                        <span>Launch</span>
                      </button>
                    )}

                    {isRunning && (
                      <button
                        onClick={() => closeSession(session.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-medium transition shadow-sm"
                      >
                        <Square className="w-3 h-3 fill-white" />
                        <span>Close & Project</span>
                      </button>
                    )}

                    {isCompleted && (
                      <button
                        onClick={() => launchSession(session.id)}
                        className="flex items-center gap-1 px-2.5 py-1 text-slate-400 hover:text-slate-200 text-xs transition"
                      >
                        Relaunch
                      </button>
                    )}
                  </div>

                  <button
                    onClick={() => handleViewGraph(session)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 rounded-lg text-xs font-medium transition shadow-glow"
                  >
                    <Share2 className="w-3 h-3 text-indigo-400" />
                    <span>View Graph</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Table View */
        <div className="glass-panel rounded-xl overflow-hidden border border-border-subtle">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-background-elevated text-slate-400 font-semibold border-b border-border-subtle">
              <tr>
                <th className="p-3.5">Session Name</th>
                <th className="p-3.5">Target URL</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5">Events Captured</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {filteredSessions.map((session) => (
                <tr key={session.id} className="hover:bg-slate-800/30 transition">
                  <td className="p-3.5 font-medium text-slate-200">{session.name}</td>
                  <td className="p-3.5 font-mono text-slate-400 max-w-xs truncate">{session.target}</td>
                  <td className="p-3.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        session.status === "RUNNING"
                          ? "bg-emerald-950 text-emerald-400 border border-emerald-500/30"
                          : session.status === "COMPLETED"
                          ? "bg-indigo-950 text-indigo-400 border border-indigo-500/30"
                          : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {session.status}
                    </span>
                  </td>
                  <td className="p-3.5 font-mono">{session.event_count || 0}</td>
                  <td className="p-3.5 text-right space-x-2">
                    {session.status === "CREATED" && (
                      <button
                        onClick={() => launchSession(session.id)}
                        className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs"
                      >
                        Launch
                      </button>
                    )}
                    {session.status === "RUNNING" && (
                      <button
                        onClick={() => closeSession(session.id)}
                        className="px-2.5 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-xs"
                      >
                        Close
                      </button>
                    )}
                    <button
                      onClick={() => handleViewGraph(session)}
                      className="px-2.5 py-1 bg-indigo-600/30 text-indigo-300 hover:bg-indigo-600/40 rounded text-xs"
                    >
                      View Graph
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
