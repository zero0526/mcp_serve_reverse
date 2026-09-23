"""CLI Entrypoint for api_lineage / MCP Serve Reverse.

Supports commands:
- run-mcp: Launch the MCP Server (stdio transport for Claude/Cursor/Antigravity).
- capture: Launch an interactive or automated browser capture session.
- replay: Dry-run or execute HTTP request replay.
- graph: Manage Property Graph (statistics, rebuild, compact).
"""

import argparse
import asyncio
import sys
import uuid
from typing import Any

from app.bootstrap import bootstrap_container
from app.domain.replay.entities import ReplayMode

# Configure UTF-8 on Windows consoles to prevent charmap encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def create_cli_parser() -> argparse.ArgumentParser:
    """Creates command line parser for the application."""
    parser = argparse.ArgumentParser(
        prog="python -m app.main",
        description="MCP Serve Reverse - Web Reverse-Engineering & API Lineage Engine CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. run-mcp
    p_mcp = subparsers.add_parser("run-mcp", help="Run MCP Server over Standard I/O (for LLM clients)")
    p_mcp.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP Transport protocol (default: stdio)",
    )
    p_mcp.add_argument("--port", type=int, default=8000, help="Port for SSE server (if transport is sse)")

    # 2. capture
    p_cap = subparsers.add_parser("capture", help="Launch a browser capture session")
    p_cap.add_argument("--target", required=True, help="Target URL to analyze (e.g. https://example.com)")
    p_cap.add_argument("--name", default="CLI Capture Session", help="Session descriptive name")
    p_cap.add_argument("--duration", type=int, default=0, help="Auto-capture duration in seconds (0 = wait for Enter key)")
    p_cap.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    p_cap.add_argument("--session-id", default=None, help="Optional custom session ID")

    # 3. replay
    p_rep = subparsers.add_parser("replay", help="Replay a captured HTTP network request")
    p_rep.add_argument("--session-id", required=True, help="Session ID containing the request")
    p_rep.add_argument("--request-id", required=True, help="Request ID to replay")
    p_rep.add_argument("--mode", choices=["dry_run", "execute"], default="dry_run", help="Replay mode (default: dry_run)")
    p_rep.add_argument("--auto-resolve", action="store_true", help="Auto-resolve and execute prerequisite auth/login requests")

    # 4. graph
    p_graph = subparsers.add_parser("graph", help="Manage Property Graph for a session")
    p_graph.add_argument("--session-id", required=True, help="Target session ID")
    p_graph.add_argument(
        "--action",
        choices=["stats", "rebuild", "compact"],
        default="stats",
        help="Graph action to perform (stats, rebuild, compact)",
    )

    return parser


async def handle_run_mcp(args: argparse.Namespace, container: Any) -> None:
    """Handles running the MCP Server."""
    await container.initialize()
    print("=" * 60, file=sys.stderr)
    print("Starting MCP Server (api_lineage) via stdio...", file=sys.stderr)
    print(f"Total Tools: {len(container.mcp_server._tool_manager._tools)}", file=sys.stderr)
    print(f"Total Resources: {len(container.mcp_server._resource_manager._templates)}", file=sys.stderr)
    print("Ready to accept connections from MCP Client (Antigravity/Claude/Cursor)...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    if args.transport == "stdio":
        container.mcp_server.run(transport="stdio")
    else:
        container.mcp_server.run(transport="sse", port=args.port)


async def handle_capture(args: argparse.Namespace, container: Any) -> None:
    """Handles browser capture session from terminal."""
    await container.initialize()
    session_id = args.session_id or f"sess_{uuid.uuid4().hex[:10]}"
    print(f"[*] Starting capture session: {session_id} - '{args.name}'")
    print(f"[*] Target URL: {args.target}")
    print(f"[*] Display Mode: {'Headless' if args.headless else 'Headful (GUI)'}")

    # Start session
    options = {
        "headless": args.headless,
        "save_screenshots": True,
        "capture_options": ["network", "storage", "cookies", "crypto", "runtime"],
    }
    res = await container.start_session_uc.execute(
        session_id=session_id,
        name=args.name,
        target=args.target,
        options=options,
    )
    print(f"[+] Browser launched successfully (engine: {res.get('engine', 'playwright')})")

    # Navigate
    browser = container.start_session_uc.active_browsers.get(session_id)
    if browser and browser._pages:
        page = browser._pages[0]
        try:
            print(f"[*] Navigating to {args.target}...")
            await page.goto(args.target, timeout=45000, wait_until="domcontentloaded")
            print("[+] Page loaded.")
        except Exception as e:
            print(f"[!] Navigation error: {e}")

    # Wait or interactive
    if args.duration > 0:
        print(f"[*] Capturing events for {args.duration} seconds...")
        await asyncio.sleep(args.duration)
    else:
        print("\n" + "=" * 60)
        print(">>> INTERACT WITH THE BROWSER (LOGIN, CLICK, NAVIGATE...) <<<")
        print(">>> PRESS ENTER ON THIS TERMINAL TO STOP CAPTURE AND CLOSE BROWSER <<<")
        print("=" * 60 + "\n")
        await asyncio.to_thread(input, "")

    # Stop session
    print("[*] Stopping capture session and synchronizing events...")
    stop_res = await container.stop_session_uc.execute(session_id=session_id)
    print(f"[+] Session stopped. Status: {stop_res.get('status')}")

    # Print summary
    stats = await container.capture_status_uc.get_session_status(session_id)
    if stats and "statistics" in stats:
        st = stats["statistics"]
        print("\n" + "=" * 50)
        print(f"SESSION SUMMARY: {session_id}")
        print(f"- HTTP Requests: {st.get('network_requests', 0)}")
        print(f"- HTTP Responses: {st.get('network_responses', 0)}")
        print(f"- Storage Operations: {st.get('storage_operations', 0)}")
        print(f"- Trace Events: {st.get('trace_events', 0)}")
        print("=" * 50)


async def handle_replay(args: argparse.Namespace, container: Any) -> None:
    """Handles replay execution from terminal."""
    await container.initialize()
    mode = ReplayMode.EXECUTE if args.mode == "execute" else ReplayMode.DRY_RUN
    print(f"[*] Preparing replay for request: {args.request_id} in session: {args.session_id}")
    print(f"[*] Mode: {mode.value.upper()}, Auto-resolve dependencies: {args.auto_resolve}")

    spec = await container.generate_replay_spec_uc.execute(
        task_id=args.session_id,
        target_request_id=args.request_id,
    )
    req, result, comparison = await container.execute_replay_uc.execute(
        spec=spec,
        mode=mode,
        session_id=args.session_id,
        auto_resolve_dependencies=args.auto_resolve,
    )

    print("\n" + "=" * 50)
    print("REPLAY REQUEST PREVIEW:")
    print(f"Method: {req.method}")
    print(f"URL: {req.url}")
    print(f"Headers: {req.headers}")
    if req.body:
        print(f"Body: {req.body}")

    if result:
        print("\nEXECUTION RESULT:")
        print(f"Success: {result.success}")
        print(f"Status Code: {result.status_code}")
        if result.error_message:
            print(f"Error: {result.error_message}")
        if comparison:
            print(f"Baseline Match: {comparison.status_match} (Diffs: {len(comparison.diffs)})")
    print("=" * 50)


async def handle_graph(args: argparse.Namespace, container: Any) -> None:
    """Handles Property Graph management from terminal."""
    await container.initialize()
    session_id = args.session_id
    action = args.action

    if action == "stats":
        nodes = await container.graph_repository.get_nodes(session_id)
        edges = await container.graph_repository.get_edges(session_id)
        print("\n" + "=" * 50)
        print(f"PROPERTY GRAPH STATS ({session_id}):")
        print(f"- Total Nodes: {len(nodes)}")
        print(f"- Total Edges: {len(edges)}")
        type_counts = {}
        for n in nodes:
            t = str(n.node_type)
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in type_counts.items():
            print(f"  + {t}: {c}")
        print("=" * 50)

    elif action == "rebuild":
        print(f"[*] Rebuilding property graph for session {session_id}...")
        res = await container.rebuild_graph_uc.execute(session_id=session_id)
        print(f"[+] Rebuild complete! Created {res.get('nodes_created', 0)} nodes, {res.get('edges_created', 0)} edges.")

    elif action == "compact":
        print(f"[*] Pruning and compacting property graph for session {session_id}...")
        res = await container.compact_graph_uc.execute(session_id=session_id)
        print(f"[+] Compact complete! Pruned {res.get('pruned_nodes', 0)} junk nodes, {res.get('pruned_edges', 0)} edges.")


def main() -> None:
    """Main CLI entrypoint."""
    parser = create_cli_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    container = bootstrap_container()

    if args.command == "run-mcp":
        asyncio.run(handle_run_mcp(args, container))
    elif args.command == "capture":
        asyncio.run(handle_capture(args, container))
    elif args.command == "replay":
        asyncio.run(handle_replay(args, container))
    elif args.command == "graph":
        asyncio.run(handle_graph(args, container))


if __name__ == "__main__":
    main()
