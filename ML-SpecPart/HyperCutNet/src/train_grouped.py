"""
Group-by-group training: run GNN once per design (ub_isolate=True) or per (design, ub)
(ub_isolate=False), then predict per solution. More efficient for val/test and for
training when solutions share structure.

Usage: same as train.py, e.g. python train_grouped.py --data_root <path> --checkpoint <name>
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import random_split
import dgl
import os
import argparse
import glob
import random
import numpy
import tee
from sklearn.metrics import precision_score, recall_score, f1_score

from parser import NODE2VEC_DIM
from graphdataset import GraphDataset, get_overlap_weights
from model import NetPredictor
from args import get_args
from checkpoint_utils import (
    load_training_checkpoint,
    prepare_checkpoint_dir,
    resolve_resume_path,
    save_training_checkpoint,
)


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Using device: {device}")
args = get_args()


def init(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    numpy.random.seed(seed)
    random.seed(seed)


def init_model(args):
    """Compute pin/net feature dims from hyperparameters and build model."""
    ub_isolate = getattr(args, 'ub_isolate', False) and getattr(args, 'use_ubfactor', False)
    pin_in_dim = int(getattr(args, 'pin_base_dim', 2)) + 2
    if getattr(args, 'use_pagerank', False):
        pin_in_dim += 1
    if getattr(args, 'use_node2vec', False):
        pin_in_dim += int(NODE2VEC_DIM)

    net_in_dim = int(getattr(args, 'net_base_dim', 1))
    if getattr(args, 'use_ubfactor', False) and not ub_isolate:
        net_in_dim += 1

    model = NetPredictor(
        pin_in_dim=pin_in_dim,
        net_in_dim=net_in_dim,
        hidden_dim=args.hidden_dim,
        out_dim=1,
        n_layers=args.layers,
        ub_isolate=ub_isolate,
        pin2net_type=getattr(args, 'pin2net_type', 'gat'),
        pin2net_gat_heads=getattr(args, 'pin2net_gat_heads', 4),
        pin2net_gat_feat_drop=getattr(args, 'pin2net_gat_feat_drop', 0.0),
        pin2net_gat_attn_drop=getattr(args, 'pin2net_gat_attn_drop', 0.0),
        pin2net_gat_chunk_nets=getattr(args, 'pin2net_gat_chunk_nets', 0),
        net2net_type=getattr(args, 'net2net_type', 'gat'),
        net2net_gat_heads=getattr(args, 'net2net_gat_heads', 4),
        net2net_gat_feat_drop=getattr(args, 'net2net_gat_feat_drop', 0.0),
        net2net_gat_attn_drop=getattr(args, 'net2net_gat_attn_drop', 0.0),
        net2pin_type=getattr(args, 'net2pin_type', 'gat'),
        net2pin_gat_heads=getattr(args, 'net2pin_gat_heads', 4),
        net2pin_gat_feat_drop=getattr(args, 'net2pin_gat_feat_drop', 0.0),
        net2pin_gat_attn_drop=getattr(args, 'net2pin_gat_attn_drop', 0.0),
    ).to(device)

    return model


def _weighted_precision_recall_f1(preds, labels, weights):
    """Compute quality-weighted precision, recall, F1."""
    pred_pos = (preds == 1)
    true_pos = (labels == 1)
    tp_w = float(numpy.sum(weights[pred_pos & true_pos]))
    fp_w = float(numpy.sum(weights[pred_pos & ~true_pos]))
    fn_w = float(numpy.sum(weights[~pred_pos & true_pos]))
    prec = tp_w / (tp_w + fp_w) if (tp_w + fp_w) > 0 else 0.0
    rec = tp_w / (tp_w + fn_w) if (tp_w + fn_w) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return prec, rec, f1


def _build_groups(dataset, indices, use_ubfactor, ub_isolate):
    """
    Group solution indices: by design_idx if ub_isolate, else by (design_idx, ub_val).
    Returns list of (group_key, [sol_idx, ...]).
    """
    if ub_isolate:
        groups = {}
        for idx in indices:
            di = dataset.solution_infos[idx]["design_idx"]
            groups.setdefault(di, []).append(idx)
    else:
        groups = {}
        for idx in indices:
            si = dataset.solution_infos[idx]
            di = si["design_idx"]
            ub = si["ub"]
            ub_val = float(ub[0, 0].item()) if ub is not None else 0.5
            groups.setdefault((di, ub_val), []).append(idx)

    return list(groups.items())


def evaluate_grouped(model, dataset, indices, device, loss_fn, args, threshold=0.5, return_predictions=False):
    """
    Evaluation with design-grouped inference: GNN once per design or per (design, ub).
    Returns (avg_loss, precision, recall, f1, w_prec, w_rec, w_f1) where w_* are None unless --eval_weighted_metrics.
    """
    model.eval()
    use_ubfactor = getattr(args, 'use_ubfactor', False)
    ub_isolate = getattr(args, 'ub_isolate', False) and use_ubfactor
    eval_weighted = getattr(args, 'eval_weighted_metrics', False)

    groups = _build_groups(dataset, indices, use_ubfactor, ub_isolate)

    total_loss = 0.0
    total_solutions = 0
    all_preds = []
    all_labels = []
    all_weights = [] if eval_weighted else None
    preds_by_sol = {} if return_predictions else None

    with torch.no_grad():
        for group_key, sol_indices in groups:
            design_idx = group_key[0] if isinstance(group_key, tuple) else group_key

            g = dataset.design_graphs[design_idx].clone()
            if not ub_isolate and use_ubfactor:
                ub_tensor = dataset.solution_infos[sol_indices[0]]["ub"]
                if ub_tensor is not None:
                    g.nodes["net"].data["feat"] = torch.cat(
                        [g.nodes["net"].data["feat"], ub_tensor], dim=1
                    )

            g = g.to(device)
            pin_feat = g.nodes["pin"].data["feat"]
            overlap_weights = get_overlap_weights(
                g,
                normalize_overlap_weights=getattr(args, 'normalize_overlap_weights', False),
            )

            h_net = model.encode(g, pin_feat, overlap_weights)

            if ub_isolate:
                for sol_idx in sol_indices:
                    ub = dataset.solution_infos[sol_idx]["ub"].to(device)
                    labels = dataset.solution_infos[sol_idx]["label"].to(device)
                    w = float(dataset.solution_infos[sol_idx]["quality_weight"])
                    logits = model.predict_from_hnet(h_net, ub=ub)
                    loss = loss_fn(logits, labels)
                    total_loss += loss.item()
                    total_solutions += 1

                    probs = torch.sigmoid(logits).squeeze()
                    preds = (probs >= threshold).long().cpu().numpy()
                    y_true = (labels.squeeze() >= threshold).long().cpu().numpy()
                    all_preds.append(preds)
                    all_labels.append(y_true)
                    if eval_weighted:
                        all_weights.append(numpy.full(preds.shape, w, dtype=numpy.float32))

                    if return_predictions:
                        net_ids = g.nodes["net"].data["id"].squeeze().cpu().numpy()
                        preds_by_sol[sol_idx] = (numpy.atleast_1d(net_ids.ravel()), preds)
            else:
                logits = model.predict_from_hnet(h_net)
                probs = torch.sigmoid(logits).squeeze()
                preds_np = (probs >= threshold).long().cpu().numpy()
                net_ids = g.nodes["net"].data["id"].squeeze().cpu().numpy()
                net_ids_1d = numpy.atleast_1d(net_ids.ravel())

                for sol_idx in sol_indices:
                    labels = dataset.solution_infos[sol_idx]["label"].to(device)
                    w = float(dataset.solution_infos[sol_idx]["quality_weight"])
                    loss = loss_fn(logits, labels)
                    total_loss += loss.item()
                    total_solutions += 1

                    y_true = (labels.squeeze() >= threshold).long().cpu().numpy()
                    all_preds.append(preds_np)
                    all_labels.append(y_true)
                    if eval_weighted:
                        all_weights.append(numpy.full(preds_np.shape, w, dtype=numpy.float32))

                    if return_predictions:
                        preds_by_sol[sol_idx] = (net_ids_1d, preds_np)

    if not all_preds:
        result = (0.0, 0.0, 0.0, 0.0, None, None, None)
        if return_predictions:
            return result, preds_by_sol
        return result

    all_preds = numpy.concatenate(all_preds)
    all_labels = numpy.concatenate(all_labels)
    precision = precision_score(all_labels, all_preds, zero_division=0)
    recall = recall_score(all_labels, all_preds, zero_division=0)
    f1 = f1_score(all_labels, all_preds, zero_division=0)
    avg_loss = total_loss / max(1, total_solutions)

    w_prec, w_rec, w_f1 = None, None, None
    if eval_weighted and all_weights:
        all_weights = numpy.concatenate(all_weights)
        w_prec, w_rec, w_f1 = _weighted_precision_recall_f1(all_preds, all_labels, all_weights)

    result = (avg_loss, precision, recall, f1, w_prec, w_rec, w_f1)
    if return_predictions:
        return result, preds_by_sol
    return result


def train_grouped(args, model):
    use_ubfactor = getattr(args, 'use_ubfactor', False)
    ub_isolate = getattr(args, 'ub_isolate', False) and use_ubfactor

    dataset = GraphDataset(
        args.data_root,
        use_node2vec=getattr(args, 'use_node2vec', False),
        use_node2vec_disk_cache=getattr(args, 'use_node2vec_disk_cache', False),
        use_pagerank=getattr(args, 'use_pagerank', False),
        use_ubfactor=use_ubfactor,
        ub_max=getattr(args, 'ub_max', 20),
        ub_isolate=ub_isolate,
        dataset_savepath=getattr(args, 'dataset_savepath', None),
        pin_struct_feat_mode=getattr(args, 'pin_struct_feat_mode', 'hetero'),
        prune_overlap_topk=getattr(args, 'prune_overlap_topk', 0),
        prune_overlap_min_weight=getattr(args, 'prune_overlap_min_weight', 0),
    )

    if len(dataset) == 0:
        print("No graphs found. Exiting.")
        return

    total_size = len(dataset)
    if total_size < 3:
        train_set = dataset
        val_set = dataset
        test_set = dataset
    else:
        train_size = int(0.8 * total_size)
        val_size = max(1, int(0.1 * total_size))
        test_size = max(1, total_size - train_size - val_size)
        train_size = total_size - val_size - test_size

        train_set, val_set, test_set = random_split(
            dataset, [train_size, val_size, test_size],
            generator=torch.Generator().manual_seed(42)
        )

    def _subset_to_indices(subset):
        if hasattr(subset, "indices"):
            return list(subset.indices)
        return list(range(len(dataset)))

    train_indices = _subset_to_indices(train_set)
    val_indices = _subset_to_indices(val_set)
    test_indices = _subset_to_indices(test_set)

    train_groups = _build_groups(dataset, train_indices, use_ubfactor, ub_isolate)

    print(f"Dataset: {total_size} solutions, {len(train_groups)} train groups")
    print(f"Split: Train {len(train_indices)}, Val {len(val_indices)}, Test {len(test_indices)}")

    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
    loss_fn_eval = nn.BCEWithLogitsLoss()
    loss_fn_none = nn.BCEWithLogitsLoss(reduction="none")

    best_val_f1 = -1.0
    start_epoch = 0
    resume_path = resolve_resume_path(args)
    if resume_path:
        start_epoch, best_val_f1 = load_training_checkpoint(
            resume_path, model, optimizer, device, default_best_val_f1=best_val_f1
        )

    batch_size = max(1, getattr(args, 'batch_size', 4))
    grouped_encode_once = getattr(args, 'grouped_encode_once', False)
    if grouped_encode_once:
        print(
            "\n--- Start Group-by-Group Training "
            "(one GNN encode per group; one optimizer step per group) ---"
        )
    else:
        print("\n--- Start Group-by-Group Training (one step per batch) ---")

    for epoch in range(start_epoch, args.epochs):
        model.train()
        random.shuffle(train_groups)
        total_train_loss = 0.0
        total_solutions = 0

        for group_key, sol_indices in train_groups:
            sol_indices = list(sol_indices)
            random.shuffle(sol_indices)
            design_idx = group_key[0] if isinstance(group_key, tuple) else group_key

            g = dataset.design_graphs[design_idx].clone()
            if not ub_isolate and use_ubfactor:
                ub_tensor = dataset.solution_infos[sol_indices[0]]["ub"]
                if ub_tensor is not None:
                    g.nodes["net"].data["feat"] = torch.cat(
                        [g.nodes["net"].data["feat"], ub_tensor], dim=1
                    )

            g = g.to(device)
            pin_feat = g.nodes["pin"].data["feat"]
            overlap_weights = get_overlap_weights(
                g,
                normalize_overlap_weights=getattr(args, 'normalize_overlap_weights', False),
            )

            batch_starts = list(range(0, len(sol_indices), batch_size))

            if grouped_encode_once:
                group_weight_sum = 0.0
                for sol_idx in sol_indices:
                    labels = dataset.solution_infos[sol_idx]["label"]
                    w = float(dataset.solution_infos[sol_idx]["quality_weight"])
                    group_weight_sum = group_weight_sum + w * labels.numel()

                if group_weight_sum <= 0:
                    total_solutions += len(sol_indices)
                    continue

                h_net = model.encode(g, pin_feat, overlap_weights)
                h_net_cached = h_net.detach().requires_grad_(True)
                optimizer.zero_grad()
                group_loss_value = 0.0

                for batch_start in batch_starts:
                    batch_sol_indices = sol_indices[batch_start : batch_start + batch_size]
                    batch_loss = h_net_cached.new_zeros(())

                    if ub_isolate:
                        for sol_idx in batch_sol_indices:
                            ub = dataset.solution_infos[sol_idx]["ub"].to(device)
                            labels = dataset.solution_infos[sol_idx]["label"].to(device)
                            w = float(dataset.solution_infos[sol_idx]["quality_weight"])
                            logits = model.predict_from_hnet(h_net_cached, ub=ub)
                            raw = loss_fn_none(logits, labels)
                            batch_loss = batch_loss + (raw * w).sum()
                    else:
                        logits = model.predict_from_hnet(h_net_cached)
                        for sol_idx in batch_sol_indices:
                            labels = dataset.solution_infos[sol_idx]["label"].to(device)
                            w = float(dataset.solution_infos[sol_idx]["quality_weight"])
                            raw = loss_fn_none(logits, labels)
                            batch_loss = batch_loss + (raw * w).sum()

                    loss = batch_loss / group_weight_sum
                    loss.backward()
                    group_loss_value += loss.item()
                    total_solutions += len(batch_sol_indices)

                if h_net_cached.grad is not None:
                    h_net.backward(h_net_cached.grad)
                    optimizer.step()
                total_train_loss += group_loss_value * len(sol_indices)
            else:
                # Split group into batches; one optimizer step per batch
                for batch_start in batch_starts:
                    batch_sol_indices = sol_indices[batch_start : batch_start + batch_size]
                    h_net = model.encode(g, pin_feat, overlap_weights)

                    optimizer.zero_grad()
                    batch_loss = 0.0
                    batch_weight_sum = 0.0

                    if ub_isolate:
                        for sol_idx in batch_sol_indices:
                            ub = dataset.solution_infos[sol_idx]["ub"].to(device)
                            labels = dataset.solution_infos[sol_idx]["label"].to(device)
                            w = float(dataset.solution_infos[sol_idx]["quality_weight"])
                            logits = model.predict_from_hnet(h_net, ub=ub)
                            raw = loss_fn_none(logits, labels)
                            batch_loss = batch_loss + (raw * w).sum()
                            batch_weight_sum = batch_weight_sum + w * labels.numel()
                    else:
                        logits = model.predict_from_hnet(h_net)
                        for sol_idx in batch_sol_indices:
                            labels = dataset.solution_infos[sol_idx]["label"].to(device)
                            w = float(dataset.solution_infos[sol_idx]["quality_weight"])
                            raw = loss_fn_none(logits, labels)
                            batch_loss = batch_loss + (raw * w).sum()
                            batch_weight_sum = batch_weight_sum + w * labels.numel()

                    if batch_weight_sum > 0:
                        loss = batch_loss / batch_weight_sum
                        loss.backward()
                        optimizer.step()
                        total_train_loss += loss.item() * len(batch_sol_indices)
                    total_solutions += len(batch_sol_indices)

        avg_train_loss = total_train_loss / max(1, total_solutions)

        if epoch % 5 == 0:
            val_loss, val_prec, val_rec, val_f1, w_prec, w_rec, w_f1 = evaluate_grouped(
                model, dataset, val_indices, device, loss_fn_eval, args
            )
            msg = (
                f"Epoch {epoch:03d} | Train Loss: {avg_train_loss:.4f} | "
                f"Val Loss: {val_loss:.4f} | Val P: {val_prec:.4f} | "
                f"Val R: {val_rec:.4f} | Val F1: {val_f1:.4f}"
            )
            if w_f1 is not None:
                msg += f" | wP: {w_prec:.4f} wR: {w_rec:.4f} wF1: {w_f1:.4f}"
            print(msg)

            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                torch.save(
                    model.state_dict(),
                    os.path.join("../checkpoints", args.checkpoint, "best_model_graph_split.pth"),
                )
                save_training_checkpoint(args, model, optimizer, epoch, best_val_f1, is_best=True)

        save_training_checkpoint(args, model, optimizer, epoch, best_val_f1)

    print("\n--- Final Testing ---")
    ckpt_dir = os.path.join('../checkpoints', args.checkpoint or 'default')
    ckpt_path = os.path.join(ckpt_dir, 'best_model_graph_split.pth')
    if os.path.exists(ckpt_path):
        model.load_state_dict(torch.load(ckpt_path, map_location=device))
    _, test_prec, test_rec, test_f1, w_prec, w_rec, w_f1 = evaluate_grouped(
        model, dataset, test_indices, device, loss_fn_eval, args
    )
    print(f"Test Precision: {test_prec:.4f} | Test Recall: {test_rec:.4f} | Test F1: {test_f1:.4f}")
    if w_f1 is not None:
        print(f"Test (weighted) wP: {w_prec:.4f} | wR: {w_rec:.4f} | wF1: {w_f1:.4f}")

    if getattr(args, 'save_predictions', False):
        pred_dir = os.path.join(ckpt_dir, 'predictions')
        os.makedirs(pred_dir, exist_ok=True)
        _, preds_by_sol = evaluate_grouped(
            model, dataset, test_indices, device, loss_fn_eval, args,
            return_predictions=True
        )
        for sol_idx, (net_ids, preds) in preds_by_sol.items():
            sol_dir = dataset.solution_infos[sol_idx]["sol_dir"]
            design_name = os.path.basename(sol_dir)
            out_path = os.path.join(pred_dir, f"{design_name}.txt")
            with open(out_path, "w") as f:
                for aid, cut in zip(net_ids, preds):
                    f.write(f"{aid} {int(cut)}\n")
        print(f"Predictions saved to {pred_dir}")


if __name__ == "__main__":
    seed = random.randint(1, 10000)
    init(seed)
    args = get_args()

    if args.checkpoint:
        print('Saving logs and models to ../checkpoints/{}'.format(args.checkpoint))
        checkpoint_path = prepare_checkpoint_dir(args)
        torch.save(args, os.path.join(checkpoint_path, 'args.pkl'))
        model = init_model(args)
        stdout_f = '../checkpoints/{}/stdout.log'.format(args.checkpoint)
        with tee.StdoutTee(stdout_f):
            print('seed:', seed)
            print(args)
            print(model)
            train_grouped(args, model)
    else:
        print('No checkpoint specified. No model checkpoints or logs.')
        model = init_model(args)
        print(args)
        print(model)
        train_grouped(args, model)
