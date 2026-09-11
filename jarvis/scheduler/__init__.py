"""Bounded local scheduler (roadmap Phase C).

Schedules persist in SQLite; `tick()` runs due jobs through caller-provided
handlers. No daemon: the operator triggers ticks via `jarvis schedule tick`
(directly or from Windows Task Scheduler).
"""
