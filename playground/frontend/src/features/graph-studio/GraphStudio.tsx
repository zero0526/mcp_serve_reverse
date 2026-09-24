import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Share2,
  Filter,
  Search,
  Maximize2,
  Download,
  RotateCcw,
  Sparkles,
  Layers,
  ArrowRight,
} from "lucide-react";
import { useStudioStore } from "../../stores/useStudioStore";
import { CustomGraphNode } from "./CustomGraphNode";
import { InspectorDrawer } from "./InspectorDrawer";
import { NodeType } from "../../types";

const nodeTypes = {
  custom: CustomGraphNode as any,
};

export const GraphStudio: React.FC = () => {
  const {
    sessions,
    selectedSessionId,
    setSelectedSessionId,
    graphNodes,
    graphEdges,
    setSelectedNode,
    filterNodeType,
    setFilterNodeType,
    searchQuery,
    setSearchQuery,
    fetchGraph,
    setActiveTab,
  } = useStudioStore();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Calculate layout coordinates for nodes
  const layoutNodes = useCallback(
    (sourceNodes: typeof graphNodes, sourceEdges: typeof graphEdges) => {
      // Group by layer: VALUE & STORAGE (layer 0) -> FUNCTION & CRYPTO (layer 1) -> REQUEST (layer 2)
      const layers: Record<number, typeof graphNodes> = { 0: [], 1: [], 2: [] };

      sourceNodes.forEach((node) => {
        if (node.node_type === "VALUE" || node.node_type === "STORAGE") {
          layers[0].push(node);
        } else if (node.node_type === "FUNCTION" || node.node_type === "CRYPTO") {
          layers[1].push(node);
        } else {
          layers[2].push(node);
        }
      });

      const flowNodes: Node[] = [];
      const colWidth = 340;
      const rowHeight = 160;

      [0, 1, 2].forEach((layerIdx) => {
        const group = layers[layerIdx];
        group.forEach((item, rowIdx) => {
          flowNodes.push({
            id: item.id,
            type: "custom",
            position: {
              x: 100 + layerIdx * colWidth,
              y: 80 + rowIdx * rowHeight,
            },
            data: {
              ...item,
            },
          });
        });
      });

      // Edges with glowing arrows
      const flowEdges: Edge[] = sourceEdges.map((e) => ({
        id: String(e.id),
        source: e.source_id,
        target: e.target_id,
        label: e.relation_type,
        labelStyle: { fill: "#94a3b8", fontSize: 10, fontWeight: 600, fontFamily: "JetBrains Mono" },
        labelBgStyle: { fill: "#0f172a", fillOpacity: 0.85 },
        labelBgPadding: [6, 2],
        labelBgBorderRadius: 4,
        animated: true,
        style: { stroke: "#6366f1", strokeWidth: 1.8 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: "#6366f1",
        },
      }));

      return { flowNodes, flowEdges };
    },
    []
  );

  // Sync state nodes with graphNodes
  useEffect(() => {
    // Filter by type & search query
    let filtered = graphNodes;
    if (filterNodeType !== "ALL") {
      filtered = filtered.filter((n) => n.node_type === filterNodeType);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (n) =>
          n.id.toLowerCase().includes(q) ||
          (n.alias && n.alias.toLowerCase().includes(q)) ||
          (n.label && n.label.toLowerCase().includes(q))
      );
    }

    const { flowNodes, flowEdges } = layoutNodes(filtered, graphEdges);
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [graphNodes, graphEdges, filterNodeType, searchQuery, layoutNodes, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const rawNode = graphNodes.find((n) => n.id === node.id);
      if (rawNode) {
        setSelectedNode(rawNode);
      }
    },
    [graphNodes, setSelectedNode]
  );

  const handleExportJson = () => {
    const dataStr =
      "data:text/json;charset=utf-8," +
      encodeURIComponent(JSON.stringify({ nodes: graphNodes, edges: graphEdges }, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `graph_${selectedSessionId || "session"}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleAutoLayout = () => {
    const { flowNodes, flowEdges } = layoutNodes(graphNodes, graphEdges);
    setNodes(flowNodes);
    setEdges(flowEdges);
  };

  return (
    <div className="relative h-[calc(100vh-3.5rem)] w-full flex flex-col bg-background-base overflow-hidden">
      {/* Canvas Top Toolbar */}
      <div className="z-20 flex flex-wrap items-center justify-between gap-3 px-6 py-3 border-b border-border-subtle bg-background-surface/80 backdrop-blur-md">
        {/* Left: Session Switcher & Stats */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Session:</span>
            <select
              value={selectedSessionId || ""}
              onChange={(e) => {
                setSelectedSessionId(e.target.value);
                fetchGraph(e.target.value);
              }}
              className="bg-background-elevated border border-border-subtle text-slate-200 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:border-indigo-500"
            >
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.status})
                </option>
              ))}
            </select>
          </div>

          <div className="hidden sm:flex items-center gap-2 text-[11px] font-mono text-slate-400 border-l border-border-subtle pl-3">
            <span>Nodes: <strong className="text-indigo-400">{graphNodes.length}</strong></span>
            <span>Edges: <strong className="text-indigo-400">{graphEdges.length}</strong></span>
          </div>
        </div>

        {/* Center: Search & Filter */}
        <div className="flex items-center gap-2">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2" />
            <input
              type="text"
              placeholder="Search node alias or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-background-elevated border border-border-subtle rounded-lg pl-8 pr-3 py-1 text-xs text-slate-200 placeholder-slate-500 w-44 sm:w-56 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* NodeType Filter */}
          <select
            value={filterNodeType}
            onChange={(e) => setFilterNodeType(e.target.value as NodeType | "ALL")}
            className="bg-background-elevated border border-border-subtle text-slate-300 rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-indigo-500"
          >
            <option value="ALL">All Types</option>
            <option value="REQUEST">REQUEST</option>
            <option value="FUNCTION">FUNCTION</option>
            <option value="CRYPTO">CRYPTO</option>
            <option value="STORAGE">STORAGE</option>
            <option value="VALUE">VALUE</option>
          </select>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleAutoLayout}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-background-elevated hover:bg-slate-800 text-slate-300 border border-border-subtle rounded-lg text-xs font-medium transition"
            title="Auto Arrange Nodes"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span className="hidden md:inline">Auto Layout</span>
          </button>

          <button
            onClick={handleExportJson}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-background-elevated hover:bg-slate-800 text-slate-300 border border-border-subtle rounded-lg text-xs font-medium transition"
            title="Export Graph JSON"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden md:inline">Export JSON</span>
          </button>
        </div>
      </div>

      {/* Main Flow Canvas or Empty State */}
      <div className="relative flex-1 w-full h-full">
        {graphNodes.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6">
            <Share2 className="h-12 w-12 text-slate-600 mb-3" />
            <h3 className="text-base font-semibold text-slate-300">No Graph Projected Yet</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm">
              Session is either in CREATED status or hasn't captured any events. Launch the browser in
              Sessions tab and close it to generate graph lineage.
            </p>
            <button
              onClick={() => setActiveTab("launcher")}
              className="mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium flex items-center gap-1.5"
            >
              <span>Go to Sessions</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            fitView
            minZoom={0.2}
            maxZoom={2.5}
            defaultEdgeOptions={{ animated: true }}
            className="bg-[#070b14]"
          >
            <Background color="#1e293b" gap={20} size={1} />
            <Controls className="!bg-slate-900 !border-slate-800" />
            <MiniMap
              nodeStrokeWidth={3}
              zoomable
              pannable
              className="!bg-slate-900/90 !border-slate-800"
            />
          </ReactFlow>
        )}

        {/* Inspector Drawer Overlay */}
        <InspectorDrawer />
      </div>
    </div>
  );
};
