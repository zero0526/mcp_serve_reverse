import React, { useState, useEffect } from "react";
import {
  X,
  Tag,
  Trash2,
  Share2,
  FileJson,
  Layers,
  ArrowRight,
  ShieldAlert,
  Save,
  Clock,
  Check,
} from "lucide-react";
import { useStudioStore } from "../../stores/useStudioStore";

export const InspectorDrawer: React.FC = () => {
  const {
    selectedNode,
    isInspectorOpen,
    setIsInspectorOpen,
    selectedSessionId,
    updateNodeAlias,
    deleteNode,
    graphEdges,
  } = useStudioStore();

  const [aliasInput, setAliasInput] = useState("");
  const [activeTab, setActiveTab] = useState<"payload" | "relations" | "raw">("payload");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    if (selectedNode) {
      setAliasInput(selectedNode.alias || "");
      setShowDeleteConfirm(false);
    }
  }, [selectedNode]);

  if (!isInspectorOpen || !selectedNode) return null;

  const handleSaveAlias = () => {
    if (!selectedSessionId) return;
    updateNodeAlias(selectedSessionId, selectedNode.id, aliasInput.trim());
  };

  const handleDelete = () => {
    if (!selectedSessionId) return;
    deleteNode(selectedSessionId, selectedNode.id);
  };

  // Find incoming & outgoing edges
  const incomingEdges = graphEdges.filter((e) => e.target_id === selectedNode.id);
  const outgoingEdges = graphEdges.filter((e) => e.source_id === selectedNode.id);

  return (
    <aside className="fixed top-14 right-0 bottom-0 w-96 z-30 bg-background-surface/95 backdrop-blur-xl border-l border-border-subtle shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
      {/* Drawer Header */}
      <div className="p-4 border-b border-border-subtle flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/30">
              {selectedNode.node_type}
            </span>
            <span className="text-xs font-mono text-slate-400 truncate max-w-[180px]">
              {selectedNode.id}
            </span>
          </div>
          <h3 className="text-sm font-bold text-slate-100 mt-1 truncate">
            {selectedNode.alias || selectedNode.label || selectedNode.id}
          </h3>
        </div>

        <button
          onClick={() => setIsInspectorOpen(false)}
          className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition"
          aria-label="Close Inspector"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Alias Editor Section */}
      <div className="p-4 border-b border-border-subtle bg-background-elevated/50">
        <label className="block text-xs font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
          <Tag className="w-3.5 h-3.5 text-indigo-400" />
          Mnemonic Alias (Tên gợi nhớ)
        </label>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="e.g. CheckoutSignatureWasm"
            value={aliasInput}
            onChange={(e) => setAliasInput(e.target.value)}
            className="flex-1 bg-background-base border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={handleSaveAlias}
            className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition shadow-sm"
          >
            <Save className="w-3 h-3" />
            <span>Save</span>
          </button>
        </div>
      </div>

      {/* Tabs Switcher */}
      <div className="flex items-center border-b border-border-subtle px-4 pt-2 gap-4 text-xs font-medium">
        <button
          onClick={() => setActiveTab("payload")}
          className={`pb-2 border-b-2 transition ${
            activeTab === "payload"
              ? "border-indigo-500 text-indigo-400 font-semibold"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Payload & Props
        </button>
        <button
          onClick={() => setActiveTab("relations")}
          className={`pb-2 border-b-2 transition flex items-center gap-1.5 ${
            activeTab === "relations"
              ? "border-indigo-500 text-indigo-400 font-semibold"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>Lineage Relations</span>
          <span className="text-[10px] px-1 rounded bg-slate-800 text-slate-400">
            {incomingEdges.length + outgoingEdges.length}
          </span>
        </button>
        <button
          onClick={() => setActiveTab("raw")}
          className={`pb-2 border-b-2 transition ${
            activeTab === "raw"
              ? "border-indigo-500 text-indigo-400 font-semibold"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Raw Entity
        </button>
      </div>

      {/* Drawer Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {activeTab === "payload" && (
          <div className="space-y-3">
            <div className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <FileJson className="w-3.5 h-3.5 text-indigo-400" />
              Node Properties
            </div>
            <pre className="p-3 rounded-lg bg-background-base border border-border-subtle text-[11px] font-mono text-emerald-300 overflow-x-auto leading-relaxed">
              {JSON.stringify(selectedNode.properties, null, 2)}
            </pre>
          </div>
        )}

        {activeTab === "relations" && (
          <div className="space-y-4 text-xs">
            {/* Incoming */}
            <div>
              <div className="font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-blue-400" />
                Incoming Origins ({incomingEdges.length})
              </div>
              {incomingEdges.length === 0 ? (
                <p className="text-slate-500 text-[11px]">No incoming parents (root source node).</p>
              ) : (
                <div className="space-y-2">
                  {incomingEdges.map((edge) => (
                    <div
                      key={edge.id}
                      className="p-2.5 rounded-lg bg-background-elevated border border-border-subtle text-[11px]"
                    >
                      <div className="flex items-center justify-between text-indigo-300 font-mono">
                        <span>{edge.relation_type}</span>
                        <span className="text-emerald-400">
                          {(edge.confidence * 100).toFixed(0)}% confidence
                        </span>
                      </div>
                      <div className="text-slate-400 mt-1 truncate">
                        From: <span className="text-slate-200 font-mono">{edge.source_id}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Outgoing */}
            <div>
              <div className="font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                Outgoing Targets ({outgoingEdges.length})
              </div>
              {outgoingEdges.length === 0 ? (
                <p className="text-slate-500 text-[11px]">No outgoing consumers (leaf node).</p>
              ) : (
                <div className="space-y-2">
                  {outgoingEdges.map((edge) => (
                    <div
                      key={edge.id}
                      className="p-2.5 rounded-lg bg-background-elevated border border-border-subtle text-[11px]"
                    >
                      <div className="flex items-center justify-between text-indigo-300 font-mono">
                        <span>{edge.relation_type}</span>
                        <span className="text-emerald-400">
                          {(edge.confidence * 100).toFixed(0)}% confidence
                        </span>
                      </div>
                      <div className="text-slate-400 mt-1 truncate">
                        To: <span className="text-slate-200 font-mono">{edge.target_id}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "raw" && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg bg-background-elevated border border-border-subtle text-xs space-y-2">
              <div>
                <span className="text-slate-500">Session ID:</span>{" "}
                <span className="text-slate-300 font-mono text-[11px]">{selectedNode.session_id}</span>
              </div>
              <div>
                <span className="text-slate-500">Entity ID:</span>{" "}
                <span className="text-slate-300 font-mono text-[11px]">
                  {selectedNode.entity_id || "N/A"}
                </span>
              </div>
              <div>
                <span className="text-slate-500">Created:</span>{" "}
                <span className="text-slate-300 font-mono text-[11px]">
                  {new Date(selectedNode.created_at_ns / 1_000_000).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Danger Zone: Delete Node */}
      <div className="p-4 border-t border-border-subtle bg-background-elevated/40">
        {!showDeleteConfirm ? (
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="w-full flex items-center justify-center gap-1.5 py-2 px-3 bg-red-950/40 hover:bg-red-950/70 text-red-400 border border-red-500/30 rounded-lg text-xs font-medium transition"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Delete Node from Graph</span>
          </button>
        ) : (
          <div className="space-y-2 p-2.5 rounded-lg bg-red-950/80 border border-red-500/60 animate-in fade-in">
            <div className="text-xs text-red-200 font-medium flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 text-red-400 shrink-0" />
              <span>Are you sure? All related edges will be pruned!</span>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleDelete}
                className="flex-1 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded text-xs font-semibold"
              >
                Yes, Delete
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
