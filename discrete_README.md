# discrete-retrieval-ablation1
A term-level fuzzy retrieval system for discrete mathematics, with ablation experiments.

## Project Description
This is a simple retrieval system based on term classification (strong terms / weak terms). Strong terms will set score to zero if missing, to guarantee the correctness of core concepts. We conduct ablation experiments to compare the performance of different scoring strategies.

## File
- discrete_main.py: main retrieval and evaluation code
- discrete_README.md: project document

## How to run
```bash
python discrete_main.py
