"""
Solution-level DataLoader wrapper for GraphDataset.

Yields fully-attached solution graphs (label/ub/quality_weight already set)
from cached design structures and per-solution tensors. No disk IO during iteration.
"""
import dgl
import torch
from torch.utils.data import Dataset


class SolutionGraphDataset(Dataset):
    """
    Wraps GraphDataset so PyTorch DataLoader can iterate over solution graphs.

    - sol_indices: subset of solution indices (e.g. train/val/test split).
    - __getitem__(i): builds graph for solution sol_indices[i], returns (graph, sol_idx).
    - Batches can mix solutions from different designs; each solution clones its design's
      structural graph and attaches its cached label/ub/quality_weight.
    """

    def __init__(self, graph_dataset, sol_indices):
        self.graph_dataset = graph_dataset
        self.sol_indices = list(sol_indices)

    def __len__(self):
        return len(self.sol_indices)

    def __getitem__(self, i):
        # i is the dataset index; sol_idx is the global solution index in GraphDataset.
        sol_idx = self.sol_indices[i]
        g = self.graph_dataset.build_solution_graph(sol_idx)
        return g, sol_idx


def collate_solution_graphs(batch):
    """
    Collate a batch of (graph, sol_idx) into (batched_dgl_graph, list of sol_idx).
    sol_idx order matches the order of graphs in the batched heterograph.
    """
    graphs, sol_indices = zip(*batch)
    batched_g = dgl.batch(list(graphs))
    return batched_g, list(sol_indices)

