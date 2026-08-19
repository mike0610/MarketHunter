"""
MarketHunter

simulation.storage

Demo / Paper Trade Simulator v1 - Slice 2: append-only SQLite
persistence and a read-only evidence query/export seam for
Simulation-owned records only. Sole durable writer for simulation
history - never a second writer for Research, Portfolio, Risk, TOP,
or Execution data.
"""
