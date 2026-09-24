import React, { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import { Globe, Code2, Lock, Database, FileCode, Tag } from "lucide-react";
import { NodeType } from "../../types";

interface CustomNodeData {
  id: string;
  node_type: NodeType;
  label?: string;
  alias?: string;
  properties: Record<string, any>;
  onSelectNode?: () => void;
}

const TYPE_CONFIG: Record<
  NodeType,
  { label: string; bg: string; border: string; glow: string; icon: React.ComponentType<any>; color: string }
> = {
  REQUEST: {
    label: "REQUEST",
    bg: "bg-blue-950/70",
    border: "border-blue-500/60",
    glow: "shadow-[0_0_15px_rgba(59,130,246,0.3)]",
    icon: Globe,
    color: "text-blue-400",
  },
  FUNCTION: {
    label: "FUNCTION",
    bg: "bg-purple-950/70",
    border: "border-purple-500/60",
    glow: "shadow-[0_0_15px_rgba(139,92,246,0.3)]",
    icon: Code2,
    color: "text-purple-400",
  },
  CRYPTO: {
    label: "CRYPTO",
    bg: "bg-amber-950/70",
    border: "border-amber-500/60",
    glow: "shadow-[0_0_15px_rgba(245,158,11,0.3)]",
    icon: Lock,
    color: "text-amber-400",
  },
  STORAGE: {
    label: "STORAGE",
    bg: "bg-emerald-950/70",
    border: "border-emerald-500/60",
    glow: "shadow-[0_0_15px_rgba(16,185,129,0.3)]",
    icon: Database,
    color: "text-emerald-400",
  },
  VALUE: {
    label: "VALUE",
    bg: "bg-slate-900/80",
    border: "border-slate-500/60",
    glow: "shadow-[0_0_15px_rgba(100,116,139,0.3)]",
    icon: FileCode,
    color: "text-slate-300",
  },
};

export const CustomGraphNode = memo(({ data, selected }: any) => {
  const nodeData = data as CustomNodeData;
  const config = TYPE_CONFIG[nodeData.node_type] || TYPE_CONFIG.VALUE;
  const IconComponent = config.icon;

  const displayTitle = nodeData.alias || nodeData.label || nodeData.id;
  const hasAlias = Boolean(nodeData.alias);

  // Subtitle preview
  let subtitle = "";
  if (nodeData.node_type === "REQUEST") {
    subtitle = `${nodeData.properties?.method || "GET"} ${nodeData.properties?.url || ""}`;
  } else if (nodeData.node_type === "FUNCTION") {
    subtitle = nodeData.properties?.function_name || nodeData.properties?.file || "";
  } else if (nodeData.node_type === "CRYPTO") {
    subtitle = `${nodeData.properties?.algorithm || ""} ${nodeData.properties?.hash || ""}`;
  } else if (nodeData.node_type === "STORAGE") {
    subtitle = `${nodeData.properties?.storage_type || "storage"}: ${nodeData.properties?.key || ""}`;
  } else {
    subtitle = String(nodeData.properties?.literal_value ?? "");
  }

  return (
    <div
      className={`min-w-[210px] max-w-[280px] rounded-xl border backdrop-blur-md p-3 transition-all duration-200 cursor-pointer ${
        config.bg
      } ${config.border} ${selected ? `ring-2 ring-indigo-400 ${config.glow}` : "hover:border-slate-400"}`}
    >
      {/* React Flow Connection Handles */}
      <Handle type="target" position={Position.Top} className="!w-2.5 !h-2.5 !bg-indigo-400 !border-slate-900" />
      <Handle type="target" position={Position.Left} className="!w-2.5 !h-2.5 !bg-indigo-400 !border-slate-900" />
      <Handle type="source" position={Position.Bottom} className="!w-2.5 !h-2.5 !bg-indigo-400 !border-slate-900" />
      <Handle type="source" position={Position.Right} className="!w-2.5 !h-2.5 !bg-indigo-400 !border-slate-900" />

      {/* Node Header */}
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-white/10">
        <div className="flex items-center gap-1.5">
          <div className={`p-1 rounded bg-black/40 ${config.color}`}>
            <IconComponent className="w-3.5 h-3.5" />
          </div>
          <span className="text-[10px] font-bold tracking-wider uppercase text-slate-300">
            {config.label}
          </span>
        </div>

        {hasAlias && (
          <span className="flex items-center gap-1 text-[9px] font-semibold bg-indigo-500/20 text-indigo-300 px-1.5 py-0.2 rounded border border-indigo-500/30">
            <Tag className="w-2.5 h-2.5" />
            alias
          </span>
        )}
      </div>

      {/* Node Title & Subtitle */}
      <div className="mt-2">
        <div className="text-xs font-bold text-slate-100 truncate" title={displayTitle}>
          {displayTitle}
        </div>
        {subtitle && (
          <div className="text-[11px] font-mono text-slate-400 truncate mt-0.5" title={subtitle}>
            {subtitle}
          </div>
        )}
      </div>

      {/* Property Snippet */}
      {nodeData.properties?.confidence !== undefined && (
        <div className="mt-2 pt-1.5 border-t border-white/5 flex items-center justify-between text-[10px] text-slate-400">
          <span>Confidence</span>
          <span className="font-mono text-emerald-400">
            {(nodeData.properties.confidence * 100).toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  );
});
