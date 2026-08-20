"""
MarketHunter

simulation.runtime

Demo / Paper Trade Simulator v1 - Slice 3: an automatic TEST-MODE
runtime foundation. One fail-closed, single-writer Simulation
runtime cycle that consumes caller-supplied candidate/forward-
observation/mechanics seams and persists only governed Simulation
events/shadow evidence through the existing SimulationRepository.
Operational health (awaiting evidence, blocked, source unavailable/
stale, failed) is never Simulation truth.
"""
