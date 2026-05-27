# Datasets Layout

This directory is organized by dataset purpose:

- `Part_Sorting/batch1/`: current Task 1 collection output.
- `Conveyor_Sorting/batch1/`: current Task 2 collection output.
- `Foam_Inlaying/batch1/`: current Task 3 collection output.
- `Packing_Box/batch1/`: current Task 4 collection output.
- `archive/<task>/`: older timestamped collection runs, kept for reference.
- `train/`: training datasets.
- `inference/`: inference and evaluation outputs.

The auto-collection scripts write to the current task `batch1` directories by default.
