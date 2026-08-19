"""
GraphDataset for hypergraph partition training.

Key design:
- One structural DGL graph per design (design_graphs), shared by all its solutions.
- Per-solution data (label, ub, quality_weight) cached in solution_infos.
- build_solution_graph(sol_idx) clones the design graph and attaches cached tensors;
  no disk IO during training iteration.
"""
import os
import re
import glob
import dgl
import torch

from parser import buildGraphStructure, load_quality_scalar, load_labels_from_hedges, infer_ub_from_path


def normalize_graph_inplace(g):
    """
    Per-graph z-score normalization. Use for inference when no dataset/design_stats available.
    Modifies g in place. Same formula as per-design norm for consistency.
    """
    pin_feat = g.nodes["pin"].data["feat"]
    pin_mean = pin_feat.mean(dim=0, keepdim=True)
    pin_std = pin_feat.std(dim=0, keepdim=True) + 1e-6
    g.nodes["pin"].data["feat"] = (pin_feat - pin_mean) / pin_std

    net_feat = g.nodes["net"].data["feat"]
    net_mean = net_feat.mean(dim=0, keepdim=True)
    net_std = net_feat.std(dim=0, keepdim=True) + 1e-6
    g.nodes["net"].data["feat"] = (net_feat - net_mean) / net_std


def get_overlap_weights(g, normalize_overlap_weights=False):
    """
    Return net-net overlap edge weights for the hetero 'overlap' relation.

    Default: return log(weight + 1) (same as original behavior).
    Optionally: additionally normalize *per design* after the log transform:
      w_norm = w_log / (mean(w_log) + eps)
    """
    if "weight" not in g.edges["overlap"].data:
        return None

    log_key = "weight_log"
    norm_key = "weight_norm"
    w_raw = g.edges["overlap"].data["weight"]
    w_log = torch.log(w_raw + 1.0)
    g.edges["overlap"].data[log_key] = w_log

    if not normalize_overlap_weights:
        return w_log

    eps = 1e-6
    w_mean = w_log.mean()
    w_norm = w_log / (w_mean + eps)
    g.edges["overlap"].data[norm_key] = w_norm
    return w_norm


def _infer_design_name(sol_dir):
    """
    Infer design name from solution directory path.
    Flat layout: ibm02_ub01_run01 -> ibm02.
    Nested layout: design/sol_dir -> design.
    """
    base = os.path.basename(sol_dir.rstrip("/"))
    m = re.match(r"(.+?)_ub\d+_run\d+$", base)
    if m:
        return m.group(1)
    return os.path.basename(os.path.dirname(sol_dir.rstrip("/")))


def _compute_quality_weights(qualities, eps=1e-6, inv_cap=1e3):
    """
    Normalize qualities into weights: lower quality (better) -> higher weight.
    Min-max on inverse quality, then mean-normalize to ~1. Returns list of weights.
    """
    inv_q_eps = 1e-6

    def inv_weight(q):
        inv = 1.0 / (float(q) + inv_q_eps)
        return min(inv_cap, max(0.0, inv))

    invs = [inv_weight(q) if q is not None else None for q in qualities]
    valid_invs = [v for v in invs if v is not None]
    if not valid_invs:
        return [1.0] * len(qualities)

    min_inv, max_inv = min(valid_invs), max(valid_invs)
    inv_range = max_inv - min_inv
    if abs(inv_range) < eps:
        return [1.0] * len(qualities)

    w_floor = 1e-3
    w_raws = []
    for inv in invs:
        if inv is None:
            w_raws.append(None)
        else:
            w_raw = (inv - min_inv) / (inv_range + eps) + w_floor
            w_raws.append(w_raw)

    mean_w = sum(w for w in w_raws if w is not None) / len([w for w in w_raws if w is not None])
    if abs(mean_w) < eps:
        mean_w = 1.0

    weights = []
    for w_raw in w_raws:
        if w_raw is None:
            weights.append(1.0)
        else:
            w = min(inv_cap, max(0.0, w_raw / (mean_w + eps)))
            weights.append(w)
    return weights


def _set_graph_quality_weight(g, w):
    """Set per-net quality_weight (used for weighted BCE)."""
    num_nets = g.num_nodes("net")
    g.nodes["net"].data["quality_weight"] = torch.full(
        (num_nets, 1), float(w), dtype=torch.float32
    )


class GraphDataset(dgl.data.DGLDataset):
    """
    Dataset over partition graphs. Scans data_root for designs and solutions.
    Layouts: flat (<design>_ubXX_runYY/) or nested (<design>/<solution>/).
    Builds one structural graph per design (stored once), and keeps a lightweight
    per-solution index. During training/eval/test we clone the structural graph
    and attach per-solution data.
    """

    def __init__(
        self,
        root_dir,
        use_node2vec=False,
        use_pagerank=False,
        use_node2vec_disk_cache=False,
        use_ubfactor=False,
        ub_max=20,
        ub_isolate=False,
        dataset_savepath=None,
        pin_struct_feat_mode='homo',
        prune_overlap_topk=0,
        prune_overlap_min_weight=0,
    ):
        self.root_dir = root_dir
        self.use_node2vec = use_node2vec
        self.use_node2vec_disk_cache = use_node2vec_disk_cache
        self.use_pagerank = use_pagerank
        self.use_ubfactor = use_ubfactor
        self.ub_max = ub_max
        self.ub_isolate = ub_isolate and use_ubfactor
        
        self.dataset_savepath = dataset_savepath
        self.pin_struct_feat_mode = pin_struct_feat_mode
        self.prune_overlap_topk = prune_overlap_topk
        self.prune_overlap_min_weight = prune_overlap_min_weight
        # design_graphs[i]: structural DGL heterograph for design i (pins, nets, edges).
        # Pin and net features are per-design z-score normalized once at load time.
        self.design_graphs = []
        # solution_infos[j]: metadata for solution j. Keys: design_idx, sol_dir,
        # quality_weight, label (tensor), ub (tensor or None). Solutions are indexed
        # contiguously: design 0's solutions 0..n0-1, design 1's solutions n0..n0+n1-1, etc.
        self.solution_infos = []
        super().__init__(name='GraphDataset')

    def _try_load_from_cache(self):
        """
        Load from disk cache if dataset_savepath was set and cache exists.
        Cache: *.design.bin (structural graphs), *.solinfos.pt (solution metadata + tensors).
        Returns True if loaded, False otherwise.
        """
        if not self.dataset_savepath:
            return False
        design_bin_path = self.dataset_savepath + ".design.bin"
        solinfos_path = self.dataset_savepath + ".solinfos.pt"
        if not (os.path.exists(design_bin_path) and os.path.exists(solinfos_path)):
            return False
        try:
            loaded, _ = dgl.load_graphs(design_bin_path)
            self.solution_infos = torch.load(solinfos_path, map_location="cpu")
            self.design_graphs = loaded
            self._normalize_design_graphs()

            # Basic sanity check: all referenced design_idx should be valid.
            max_design_idx = len(self.design_graphs) - 1
            for si in self.solution_infos:
                if si["design_idx"] > max_design_idx:
                    raise RuntimeError("Cached solution_infos references missing design graph.")

            print(
                f"Loaded prebuilt dataset from {self.dataset_savepath} "
                f"(designs={len(self.design_graphs)}, solutions={len(self.solution_infos)})"
            )
            return True
        except Exception as e:
            print(f"Failed to load prebuilt dataset, rebuilding from rawdata: {e}")
            return False

    def _discover_designs(self):
        """Scan root_dir for designs and solutions. Returns {design_name: [sol_dirs]}."""
        all_nodes = sorted(glob.glob(
            os.path.join(self.root_dir, "**", "nodes.txt"), recursive=True
        ))
        solution_dirs = [os.path.dirname(p) for p in all_nodes]
        design_to_solutions = {}
        for sol_dir in solution_dirs:
            design = _infer_design_name(sol_dir)
            design_to_solutions.setdefault(design, []).append(sol_dir)
        for design in design_to_solutions:
            design_to_solutions[design] = sorted(design_to_solutions[design])
        return design_to_solutions

    def _build_design_graphs(self, design_name, solution_dirs):
        """
        Build one structural graph for this design and cache per-solution tensors.
        Disk IO happens here (hedges.txt, quality.txt); training later uses cached data only.
        """
        rep_sol_dir = solution_dirs[0]
        try:
            base_g = buildGraphStructure(
                rep_sol_dir,
                use_node2vec=self.use_node2vec,
                use_pagerank=self.use_pagerank,
                use_node2vec_disk_cache=self.use_node2vec_disk_cache,
                pin_struct_feat_mode=self.pin_struct_feat_mode,
                prune_overlap_topk=self.prune_overlap_topk,
                prune_overlap_min_weight=self.prune_overlap_min_weight,
            )
        except Exception as e:
            print(f"Failed to build structure for {design_name} ({rep_sol_dir}): {e}")
            return
        if base_g is None:
            print(f"Failed to build structure for {design_name} ({rep_sol_dir})")
            return

        num_nets = base_g.num_nodes("net")
        sol_entries = []   # per-solution: {sol_dir, label, ub}
        design_qualities = []  # for quality-based weighting

        # Load labels and optional ub from disk once per solution.
        for sol_dir in solution_dirs:
            edges_path = os.path.join(sol_dir, "hedges.txt")
            if not os.path.exists(edges_path):
                continue
            try:
                labels = load_labels_from_hedges(edges_path)
            except Exception:
                continue
            if labels.shape[0] != num_nets:
                continue

            q = load_quality_scalar(sol_dir, labels=labels)
            ub_tensor = None
            if self.use_ubfactor:
                ub_val = infer_ub_from_path(sol_dir)
                ub_norm = float(ub_val) / max(int(self.ub_max), 1)
                ub_tensor = torch.full((num_nets, 1), ub_norm, dtype=torch.float32)

            sol_entries.append(
                {
                    "sol_dir": sol_dir,
                    "label": labels,
                    "ub": ub_tensor,
                }
            )
            design_qualities.append(q)

        if not sol_entries:
            return

        # Assign design_idx: index of this design's structural graph.
        weights = _compute_quality_weights(design_qualities)
        design_idx = len(self.design_graphs)
        self.design_graphs.append(base_g)

        # Append one solution_info per valid solution; all share the same design_idx.
        for sol_entry, w in zip(sol_entries, weights):
            sol_dir = sol_entry["sol_dir"]
            self.solution_infos.append(
                {
                    "design_idx": design_idx,
                    "sol_dir": sol_dir,
                    "quality_weight": float(w),
                    "label": sol_entry["label"],
                    "ub": sol_entry["ub"],
                }
            )

        print(f"Loaded design {design_name}: {len(sol_entries)} solutions (struct reused)")

    def _normalize_design_graphs(self):
        """Apply per-design z-score normalization once. Modifies design_graphs in place."""
        for g in self.design_graphs:
            normalize_graph_inplace(g)

    def build_solution_graph(self, sol_idx):
        """
        Build a complete solution graph: clone design structure + attach cached tensors.
        No disk IO; used by DataLoader during training/eval.
        """
        sol_info = self.solution_infos[sol_idx]
        design_idx = sol_info["design_idx"]  # which structural graph this solution belongs to
        g = self.design_graphs[design_idx].clone()

        # Labels are always needed for training/eval.
        g.nodes["net"].data["label"] = sol_info["label"]

        # UB feature handling (matches attachSolutionData semantics).
        if self.use_ubfactor:
            ub_tensor = sol_info["ub"]
            if ub_tensor is None:
                # Defensive fallback (should not happen if use_ubfactor=True)
                ub_tensor = torch.full(
                    (g.num_nodes("net"), 1), 0.5, dtype=torch.float32
                )

            if self.ub_isolate:
                g.nodes["net"].data["ub"] = ub_tensor
            else:
                # Mixed mode: append ub_norm to net feature.
                g.nodes["net"].data["feat"] = torch.cat(
                    [g.nodes["net"].data["feat"], ub_tensor], dim=1
                )

        # Weighted BCE uses per-net quality weight.
        num_nets = g.num_nodes("net")
        g.nodes["net"].data["quality_weight"] = torch.full(
            (num_nets, 1), float(sol_info["quality_weight"]), dtype=torch.float32
        )

        return g

    def _save_to_cache(self):
        if (
            not self.dataset_savepath
            or len(self.design_graphs) == 0
            or len(self.solution_infos) == 0
        ):
            return
        design_bin_path = self.dataset_savepath + ".design.bin"
        solinfos_path = self.dataset_savepath + ".solinfos.pt"
        try:
            out_dir = os.path.dirname(self.dataset_savepath)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            dgl.save_graphs(design_bin_path, self.design_graphs)
            torch.save(self.solution_infos, solinfos_path)
            print(f"Saved generated dataset to {self.dataset_savepath}")
        except Exception as e:
            print(f"Warning: failed to save dataset to {self.dataset_savepath}: {e}")

    def process(self):
        print(f"Scanning {self.root_dir} for designs...")

        if self._try_load_from_cache():
            return

        design_to_solutions = self._discover_designs()
        design_names = sorted(design_to_solutions.keys())
        print(f"Found {len(design_names)} designs.")

        for design_name in design_names:
            self._build_design_graphs(design_name, design_to_solutions[design_name])

        self._normalize_design_graphs()
        print(
            f"Successfully loaded structural designs={len(self.design_graphs)}, "
            f"solutions={len(self.solution_infos)}."
        )
        self._save_to_cache()

    def __getitem__(self, i):
        """Return solution metadata (used by random_split; not the graph)."""
        return self.solution_infos[i]

    def __len__(self):
        """Number of solutions (not designs)."""
        return len(self.solution_infos)
