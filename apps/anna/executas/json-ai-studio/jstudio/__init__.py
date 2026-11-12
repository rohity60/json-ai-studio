"""JSON AI Studio — Anna Executa adapters (ADR-0026).

The engine itself (gateway, turn planner, diff engine, services) is the
shared ``json_ai_studio`` package. This package only adapts it to the
Anna host: LLM calls via sampling, sessions in Anna Persistent Storage,
and tool handlers over stdio JSON-RPC.
"""
