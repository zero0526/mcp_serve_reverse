import React from "react";
import {
  Sparkles,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  Clock,
  CheckCircle,
  FileCode,
  Activity,
  Layers,
  Award,
} from "lucide-react";
import { useStudioStore } from "../../stores/useStudioStore";

export const EvolutionDashboard: React.FC = () => {
  const { evolutionSummary, sessionLogs, selectedTaskId, tasks } = useStudioStore();

  const currentTask = tasks.find((t) => t.id === selectedTaskId);
  const summary = evolutionSummary;

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-6">
        <Sparkles className="h-12 w-12 text-slate-600 mb-3" />
        <h3 className="text-base font-semibold text-slate-300">No Evolution Data Available</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Run agent tasks with MCP retrospective logging to evaluate tools and synthesize proposals.
        </p>
      </div>
    );
  }

  const maxMissingFreq = Math.max(
    ...(summary.top_missing_tools.map((t) => t.frequency) || [1]),
    1
  );

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Top Header Card */}
      <div className="glass-panel rounded-xl p-5 border border-border-subtle flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-amber-950/80 text-amber-400 border border-amber-500/30">
              AI Evolution
            </span>
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              MCP Capabilities Self-Evolution Dashboard
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Agent introspective feedback, missing tools synthesis, and adaptive tool proposals.
          </p>
        </div>

        {currentTask && (
          <div className="text-xs font-mono text-slate-400 bg-background-elevated px-3 py-1.5 rounded-lg border border-border-subtle">
            Filtering Task: <strong className="text-indigo-400">{currentTask.name}</strong>
          </div>
        )}
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1 */}
        <div className="glass-panel rounded-xl p-4 border border-border-subtle">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Total Retrospectives</span>
            <Activity className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 mt-2 font-mono">
            {summary.total_retrospectives}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Recorded post-session evaluations</div>
        </div>

        {/* KPI 2 */}
        <div className="glass-panel rounded-xl p-4 border border-border-subtle">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Avg Tool Efficiency</span>
            <Award className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 mt-2 font-mono flex items-baseline gap-1">
            {summary.average_efficiency_rating.toFixed(1)}
            <span className="text-xs font-normal text-slate-500">/ 10</span>
          </div>
          {/* Rating Progress Bar */}
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
            <div
              className="bg-emerald-500 h-full rounded-full transition-all duration-500"
              style={{ width: `${(summary.average_efficiency_rating / 10) * 100}%` }}
            />
          </div>
        </div>

        {/* KPI 3 */}
        <div className="glass-panel rounded-xl p-4 border border-border-subtle">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Missing Tools Noted</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400 mt-2 font-mono">
            {summary.top_missing_tools.length}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Gaps flagged by AI agent runs</div>
        </div>

        {/* KPI 4 */}
        <div className="glass-panel rounded-xl p-4 border border-border-subtle">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Synthesized Proposals</span>
            <Lightbulb className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-indigo-400 mt-2 font-mono">
            {summary.recent_proposals.length}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Auto-designed MCP schema specs</div>
        </div>
      </div>

      {/* Center 2-Column Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Top Missing Tools Frequency */}
        <div className="lg:col-span-6 glass-panel rounded-xl p-5 border border-border-subtle">
          <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-amber-400" />
              Top Missing MCP Tools Frequency
            </h3>
            <span className="text-[11px] text-slate-500 font-mono">Occurrence</span>
          </div>

          <div className="mt-4 space-y-3">
            {summary.top_missing_tools.map((item, idx) => {
              const percentage = (item.frequency / maxMissingFreq) * 100;
              return (
                <div key={idx} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-slate-200 font-medium">{item.tool}</span>
                    <span className="text-amber-400 font-mono font-bold">{item.frequency} hits</span>
                  </div>
                  <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden border border-border-subtle">
                    <div
                      className="bg-gradient-to-r from-amber-500 to-amber-400 h-full rounded-full transition-all duration-500"
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Common Bottlenecks */}
        <div className="lg:col-span-6 glass-panel rounded-xl p-5 border border-border-subtle">
          <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              Observed Bottlenecks
            </h3>
          </div>

          <div className="mt-4 space-y-3">
            {summary.common_bottlenecks.map((item, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg bg-background-elevated border border-border-subtle flex items-start gap-3"
              >
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-red-950/80 text-red-400 border border-red-500/30 shrink-0 mt-0.5">
                  {item.frequency}x
                </span>
                <p className="text-xs text-slate-300 leading-relaxed">{item.bottleneck}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Synthesized Tool Proposals Board */}
      <div className="glass-panel rounded-xl p-5 border border-border-subtle">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-indigo-400" />
            Synthesized MCP Tool Proposals (Candidate Evolution)
          </h3>
          <span className="text-xs text-slate-500">Ready for automated synthesis</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          {summary.recent_proposals.map((prop, idx) => (
            <div
              key={idx}
              className="p-4 rounded-xl bg-background-elevated border border-indigo-500/20 hover:border-indigo-500/40 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-indigo-300">{prop.name}</span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-500/30">
                    PROPOSED
                  </span>
                </div>

                <p className="text-xs text-slate-300 mt-2 leading-relaxed">{prop.purpose}</p>

                {prop.parameters && (
                  <div className="mt-3 bg-background-base p-2 rounded-lg border border-border-subtle">
                    <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                      Parameters Schema:
                    </div>
                    <pre className="text-[11px] font-mono text-emerald-300 overflow-x-auto">
                      {JSON.stringify(prop.parameters, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {prop.expected_output && (
                <div className="mt-3 pt-2 border-t border-border-subtle text-[11px] text-slate-400">
                  <span className="text-slate-500">Expected:</span> {prop.expected_output}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Retrospective Log Stream Feed */}
      <div className="glass-panel rounded-xl p-5 border border-border-subtle">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            Agent Retrospective Feed ({sessionLogs.length})
          </h3>
        </div>

        <div className="space-y-4 mt-4">
          {sessionLogs.map((log) => (
            <div
              key={log.id}
              className="p-4 rounded-xl bg-background-elevated border border-border-subtle text-xs space-y-2.5"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-slate-400">{log.id}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                    Task: {log.task_id}
                  </span>
                </div>
                <div className="flex items-center gap-1 font-mono text-emerald-400 font-semibold">
                  <span>Rating: {log.efficiency_rating.toFixed(1)}/10</span>
                </div>
              </div>

              <p className="text-slate-200 leading-relaxed bg-background-base/50 p-3 rounded-lg border border-border-subtle">
                "{log.agent_evaluation}"
              </p>

              <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px]">
                <span className="text-slate-500">Missing Tools:</span>
                {log.missing_tools.map((t, i) => (
                  <span
                    key={i}
                    className="font-mono bg-amber-950/40 text-amber-300 border border-amber-500/20 px-1.5 py-0.2 rounded"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
