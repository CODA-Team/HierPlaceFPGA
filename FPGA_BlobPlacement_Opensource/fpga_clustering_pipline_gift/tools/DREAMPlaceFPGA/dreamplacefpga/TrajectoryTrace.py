# TrajectoryTrace.py
import os
import logging
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _norm_name(x):
    """Normalize node name to python str."""
    try:
        # numpy.bytes_ / bytes
        if isinstance(x, (bytes, np.bytes_)):
            return x.decode("utf-8", errors="ignore")
    except Exception:
        pass
    return str(x)


class CellTrajectoryTracer:
    """
    追踪一组 cell 的 (x,y) 轨迹，并输出：
      - trace_cells.npz  (iters, node_ids, node_names, traj[T,K,2])
      - trace_cells.png  (轨迹图)
    选点方式：默认从 init pl 文件（movable_init.pl）按文件顺序取前 K 个（且必须是 movable）。
    """
    def __init__(self, placedb, params,
                 num_cells=10,
                 interval=1,
                 init_pl_path=None,
                 node_ids=None):
        self.num_nodes = int(placedb.num_nodes)
        self.num_movable = int(placedb.num_movable_nodes)
        self.interval = max(1, int(interval))

        # 1) 硬指定 node_ids（最高优先级）
        if node_ids is not None:
            ids = np.asarray(node_ids, dtype=np.int32)
            ids = ids[(ids >= 0) & (ids < self.num_nodes)]
            if ids.size == 0:
                raise ValueError("No valid node_ids for tracing.")
            self.node_ids = ids
        else:
            # 2) 从 init pl 文件选前 K 个 movable
            k = max(1, int(num_cells))
            self.node_ids = self._select_from_init_pl(placedb, init_pl_path, k)

        # names
        self.node_names = [_norm_name(placedb.node_names[i]) for i in self.node_ids]

        self.iters = []
        self.xys = []  # list of [K,2]

    def _select_from_init_pl(self, placedb, init_pl_path, k):
        """
        从 movable_init.pl（或 params.init_placement_file）读取，按文件顺序取前 k 个 movable 单元。
        文件行格式： name x y z ...
        """
        if not init_pl_path:
            init_pl_path = getattr(params, "init_placement_file", "")  # 兼容你工程里的参数
        if not init_pl_path:
            init_pl_path = "movable_init.pl"

        picked = []
        picked_set = set()

        if os.path.isfile(init_pl_path):
            with open(init_pl_path, "r") as f:
                for line in f:
                    s = line.strip()
                    if (not s) or s.startswith("#"):
                        continue
                    tokens = s.replace(":", " ").split()
                    if len(tokens) < 1:
                        continue
                    name = tokens[0]

                    # 用 placedb.node_name2id_map 映射到 node_id
                    node_id = placedb.node_name2id_map.get(name, None)
                    if node_id is None:
                        continue

                    # 只追踪 movable（你要求的）
                    if node_id >= self.num_movable:
                        continue

                    if node_id not in picked_set:
                        picked.append(int(node_id))
                        picked_set.add(int(node_id))

                    if len(picked) >= k:
                        break

            if len(picked) == 0:
                logging.warning("[TraceCells] init pl loaded but no matched movable nodes: %s", init_pl_path)
        else:
            logging.warning("[TraceCells] init pl not found: %s", init_pl_path)

        # 如果文件里不足 k 个，补齐为前几个 movable（不随机）
        if len(picked) < k:
            for i in range(min(self.num_movable, k * 10)):  # 给点余量避免全重复
                if i not in picked_set:
                    picked.append(i)
                    picked_set.add(i)
                if len(picked) >= k:
                    break

        picked = np.asarray(picked[:k], dtype=np.int32)
        logging.info("[TraceCells] picked %d nodes from %s (movable only)", len(picked), init_pl_path)
        return picked

    def record(self, iteration, pos):
        if (int(iteration) % self.interval) != 0:
            return

        # torch -> numpy
        if hasattr(pos, "detach"):
            t = pos.detach()
            if getattr(t, "is_cuda", False):
                t = t.cpu()
            t = t.numpy()
        else:
            t = np.asarray(pos)

        x = t[self.node_ids]
        y = t[self.num_nodes + self.node_ids]

        self.iters.append(int(iteration))
        self.xys.append(np.stack([x, y], axis=1).astype(np.float32))

    def finalize(self, out_dir, prefix="trace_cells", bounds=None):
        os.makedirs(out_dir, exist_ok=True)

        iters = np.asarray(self.iters, dtype=np.int32)
        if len(self.xys) == 0:
            raise RuntimeError("No samples recorded. Check interval / where record() is called.")

        traj = np.stack(self.xys, axis=0)  # [T,K,2]

        np.savez_compressed(
            os.path.join(out_dir, f"{prefix}.npz"),
            iters=iters,
            node_ids=self.node_ids,
            node_names=np.asarray(self.node_names),
            traj=traj
        )

        fig = plt.figure(figsize=(8, 8), dpi=160)
        ax = fig.add_subplot(111)

        if bounds is not None:
            xl, xh, yl, yh = bounds
            ax.set_xlim([xl, xh])
            ax.set_ylim([yl, yh])
            ax.add_patch(plt.Rectangle((xl, yl), xh - xl, yh - yl, fill=False, linewidth=1))

        T, K, _ = traj.shape
        for k in range(K):
            xy = traj[:, k, :]
            ax.plot(xy[:, 0], xy[:, 1], linewidth=1, alpha=0.8)
            ax.scatter([xy[0, 0]], [xy[0, 1]], s=10, marker="o")
            ax.scatter([xy[-1, 0]], [xy[-1, 1]], s=18, marker="x")

        ax.set_aspect("equal", adjustable="box")
        ax.set_title(f"Cell trajectories (K={K}, T={T})")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f"{prefix}.png"))
        plt.close(fig)
