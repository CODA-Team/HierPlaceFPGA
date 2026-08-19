import argparse


def get_args(args=None):
    parser = argparse.ArgumentParser()
    # 这里的 data_root 是包含多个 design/graph 的顶层目录
    parser.add_argument('--data_root', type=str, required=True, default='../rawdata',help='Root directory containing all graphs')
    parser.add_argument('--checkpoint', type=str, help='Directory to save the model')
    parser.add_argument('--resume', action='store_true',
                        help='Resume training from ../checkpoints/<checkpoint>/last_checkpoint.pth. Falls back to best checkpoints if needed.')
    parser.add_argument('--resume_from', type=str, default=None,
                        help='Path to a checkpoint file or checkpoint directory to resume/load before training.')
    parser.add_argument('--batch_size', type=int, default=4, help='Number of graphs per batch')
    parser.add_argument('--pin_base_dim', type=int, default=2,
                        help='Base pin feature dim from nodes.txt before structural extras')
    parser.add_argument('--net_base_dim', type=int, default=1,
                        help='Base net feature dim before optional ub feature')
    parser.add_argument('--hidden_dim', type=int, default=128)
    parser.add_argument('--layers', type=int, default=3)
    parser.add_argument('--epochs', type=int, default=200)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--use_node2vec', action='store_true',
                        help='If set, compute and append node2vec pin features inside parser.buildGraphStructure')
    parser.add_argument('--use_node2vec_disk_cache', action='store_true',
                        help='If set with --use_node2vec, load/save node2vec embedding from disk cache')
    parser.add_argument('--use_pagerank', action='store_true',
                        help='If set, compute and append PageRank as pin node feature')
    parser.add_argument(
        '--pin_struct_feat_mode',
        type=str,
        default='hetero',
        choices=['homo', 'hetero'],
        help='How to compute pin structural features (clustering/2nd-order degree, and '
             'PageRank when enabled). "homo" matches the original implementation using '
             'pin-pin clique projection; "hetero" computes analogous features on the '
             'heterogeneous pin-net graph to avoid huge-net clique blowups.'
    )
    parser.add_argument(
        '--prune_overlap_topk',
        type=int,
        default=0,
        help='Prune the net-net overlap graph edges (net->net). If > 0, keep only '
             'the top-K highest-overlap neighbors for each source net. 0 disables.'
    )
    parser.add_argument(
        '--prune_overlap_min_weight',
        type=int,
        default=0,
        help='Prune net-net overlap edges with raw overlap count < this threshold. '
             'Use 0 to disable (keep all).'
    )
    parser.add_argument(
        '--normalize_overlap_weights',
        action='store_true',
        help='Normalize net-net overlap edge weights per design before using them '
             'as GraphConv edge weights (after log(weight+1)).'
    )
    parser.add_argument('--use_ubfactor', action='store_true',
                        help='If set, append normalized UB factor as an extra net feature')
    parser.add_argument('--ub_isolate', action='store_true',
                        help='When set with use_ubfactor: keep ub out of GNN, apply only at predictor. '
                             'Better for transfer across ub. Default: False (ub mixed with structure).')
    parser.add_argument('--ub_max', type=int, default=20,
                        help='Maximum UB used to normalize UB feature: ub_norm = ub/ub_max')
    parser.add_argument('--save_predictions', action='store_true',
                        help='If set, write per-design prediction txt files during test (net_id cut_or_not per line)')
    parser.add_argument('--dataset_savepath', type=str, default=None,
                        help='Optional dataset prefix path for loading/saving prebuilt GraphDataset')
    parser.add_argument('--eval_weighted_metrics', action='store_true',
                        help='If set, also compute and report quality-weighted precision/recall/F1')
    parser.add_argument('--grouped_encode_once', action='store_true',
                        help='Only for train_grouped.py: encode each design group once, reuse h_net across solution loss chunks, and update once per group.')
    parser.add_argument('--pin2net_type', type=str, default='gat', choices=['graphconv', 'gat'],
                        help='Pin-to-net aggregation type. src4 defaults to gat for all-GAT experiments.')
    parser.add_argument('--pin2net_gat_heads', type=int, default=4,
                        help='Number of attention heads for --pin2net_type gat. hidden_dim must be divisible by this value.')
    parser.add_argument('--pin2net_gat_feat_drop', type=float, default=0.0,
                        help='Feature dropout inside DGL GATConv for pin-to-net attention.')
    parser.add_argument('--pin2net_gat_attn_drop', type=float, default=0.0,
                        help='Attention dropout inside DGL GATConv for pin-to-net attention.')
    parser.add_argument('--pin2net_gat_chunk_nets', type=int, default=0,
                        help='If >0 and --pin2net_type gat, run pin-to-net GAT in chunks of this many destination nets to reduce peak GPU memory.')
    parser.add_argument('--net2net_type', type=str, default='gat', choices=['graphconv', 'gat'],
                        help='Net-to-net overlap aggregation type. src4 defaults to gat for all-GAT experiments.')
    parser.add_argument('--net2net_gat_heads', type=int, default=4,
                        help='Number of attention heads for --net2net_type gat. hidden_dim must be divisible by this value.')
    parser.add_argument('--net2net_gat_feat_drop', type=float, default=0.0,
                        help='Feature dropout inside DGL GATConv for net-to-net attention.')
    parser.add_argument('--net2net_gat_attn_drop', type=float, default=0.0,
                        help='Attention dropout inside DGL GATConv for net-to-net attention.')
    parser.add_argument('--net2pin_type', type=str, default='gat', choices=['graphconv', 'gat'],
                        help='Net-to-pin aggregation type. src4 defaults to gat for all-GAT experiments.')
    parser.add_argument('--net2pin_gat_heads', type=int, default=4,
                        help='Number of attention heads for --net2pin_type gat. hidden_dim must be divisible by this value.')
    parser.add_argument('--net2pin_gat_feat_drop', type=float, default=0.0,
                        help='Feature dropout inside DGL GATConv for net-to-pin attention.')
    parser.add_argument('--net2pin_gat_attn_drop', type=float, default=0.0,
                        help='Attention dropout inside DGL GATConv for net-to-pin attention.')

    args = parser.parse_args()
    return args
