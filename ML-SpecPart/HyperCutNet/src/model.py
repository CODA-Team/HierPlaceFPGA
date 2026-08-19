import torch
import dgl
import torch.nn as nn
import torch.nn.functional as F
import dgl.nn as dglnn


class ThreeStageGNNLayer(nn.Module):
    def __init__(
        self,
        hidden_dim,
        pin2net_type="gat",
        pin2net_gat_heads=4,
        pin2net_gat_feat_drop=0.0,
        pin2net_gat_attn_drop=0.0,
        pin2net_gat_chunk_nets=0,
        net2net_type="gat",
        net2net_gat_heads=4,
        net2net_gat_feat_drop=0.0,
        net2net_gat_attn_drop=0.0,
        net2pin_type="gat",
        net2pin_gat_heads=4,
        net2pin_gat_feat_drop=0.0,
        net2pin_gat_attn_drop=0.0,
    ):
        super().__init__()
        self.pin2net_type = pin2net_type
        self.net2net_type = net2net_type
        self.net2pin_type = net2pin_type
        self.pin2net_gat_chunk_nets = max(0, int(pin2net_gat_chunk_nets or 0))

        # Stage 1: Pin -> Net
        self.conv_pin2net = self._build_stage_conv(
            hidden_dim,
            pin2net_type,
            pin2net_gat_heads,
            pin2net_gat_feat_drop,
            pin2net_gat_attn_drop,
            "pin2net",
            bipartite=True,
        )

        # Stage 2: Net <-> Net
        self.conv_net2net = self._build_stage_conv(
            hidden_dim,
            net2net_type,
            net2net_gat_heads,
            net2net_gat_feat_drop,
            net2net_gat_attn_drop,
            "net2net",
            bipartite=False,
        )

        # Stage 3: Net -> Pin
        self.conv_net2pin = self._build_stage_conv(
            hidden_dim,
            net2pin_type,
            net2pin_gat_heads,
            net2pin_gat_feat_drop,
            net2pin_gat_attn_drop,
            "net2pin",
            bipartite=True,
        )

        self.norm_net_1 = nn.LayerNorm(hidden_dim)
        self.norm_net_2 = nn.LayerNorm(hidden_dim)
        self.norm_pin = nn.LayerNorm(hidden_dim)

    @staticmethod
    def _build_stage_conv(hidden_dim, conv_type, gat_heads, gat_feat_drop, gat_attn_drop, stage_name, bipartite):
        if conv_type == "graphconv":
            return dglnn.GraphConv(hidden_dim, hidden_dim, norm='right', allow_zero_in_degree=True)
        if conv_type == "gat":
            if hidden_dim % gat_heads != 0:
                raise ValueError(
                    f"hidden_dim ({hidden_dim}) must be divisible by "
                    f"{stage_name}_gat_heads ({gat_heads})"
                )
            in_feats = (hidden_dim, hidden_dim) if bipartite else hidden_dim
            return dglnn.GATConv(
                in_feats,
                hidden_dim // gat_heads,
                num_heads=gat_heads,
                feat_drop=gat_feat_drop,
                attn_drop=gat_attn_drop,
                allow_zero_in_degree=True,
            )
        raise ValueError(f"Unknown {stage_name}_type: {conv_type}")

    @staticmethod
    def _flatten_gat_output(x, conv_type):
        return x.flatten(1) if conv_type == "gat" else x

    def _run_pin2net_conv(self, subg_p2n, h_pin, h_net):
        if self.pin2net_type != "gat" or self.pin2net_gat_chunk_nets <= 0:
            return self.conv_pin2net(subg_p2n, (h_pin, h_net))

        num_nets = h_net.shape[0]
        chunk_size = self.pin2net_gat_chunk_nets
        _, edge_dst = subg_p2n.edges()
        res_net = h_net.new_zeros(h_net.shape)

        for start in range(0, num_nets, chunk_size):
            end = min(start + chunk_size, num_nets)
            edge_mask = (edge_dst >= start) & (edge_dst < end)
            edge_ids = torch.nonzero(edge_mask, as_tuple=False).flatten()
            if edge_ids.numel() == 0:
                continue

            chunk_graph = dgl.edge_subgraph(subg_p2n, edge_ids, relabel_nodes=True)
            src_nodes = chunk_graph.nodes['pin'].data[dgl.NID]
            dst_nodes = chunk_graph.nodes['net'].data[dgl.NID]
            chunk_out = self.conv_pin2net(chunk_graph, (h_pin[src_nodes], h_net[dst_nodes]))
            chunk_out = self._flatten_gat_output(chunk_out, self.pin2net_type)
            res_net[dst_nodes] = chunk_out

        return res_net

    def forward(self, g, h_pin, h_net, overlap_weights):

        # 1. Pin -> Net
        subg_p2n = g[('pin', 'connected', 'net')]
        res_net_1 = self._run_pin2net_conv(subg_p2n, h_pin, h_net)
        res_net_1 = self._flatten_gat_output(res_net_1, self.pin2net_type)
        h_net = self.norm_net_1(h_net + res_net_1)
        h_net = F.relu(h_net)

        # 2. Net <-> Net
        subg_n2n = g[('net', 'overlap', 'net')]
        if self.net2net_type == "graphconv":
            res_net_2 = self.conv_net2net(subg_n2n, h_net, edge_weight=overlap_weights)
        else:
            # GATConv learns edge attention internally; overlap weights are used only by GraphConv.
            res_net_2 = self.conv_net2net(subg_n2n, h_net)
        res_net_2 = self._flatten_gat_output(res_net_2, self.net2net_type)
        h_net = self.norm_net_2(h_net + res_net_2)
        h_net = F.relu(h_net)

        # 3. Net -> Pin
        subg_n2p = g[('net', 'connected', 'pin')]
        res_pin = self.conv_net2pin(subg_n2p, (h_net, h_pin))
        res_pin = self._flatten_gat_output(res_pin, self.net2pin_type)
        h_pin = self.norm_pin(h_pin + res_pin)
        h_pin = F.relu(h_pin)

        return h_pin, h_net


class NetPredictor(nn.Module):
    def __init__(
        self,
        pin_in_dim,
        net_in_dim,
        hidden_dim,
        out_dim,
        n_layers=3,
        dropout=0.2,
        ub_isolate=False,
        pin2net_type="gat",
        pin2net_gat_heads=4,
        pin2net_gat_feat_drop=0.0,
        pin2net_gat_attn_drop=0.0,
        pin2net_gat_chunk_nets=0,
        net2net_type="gat",
        net2net_gat_heads=4,
        net2net_gat_feat_drop=0.0,
        net2net_gat_attn_drop=0.0,
        net2pin_type="gat",
        net2pin_gat_heads=4,
        net2pin_gat_feat_drop=0.0,
        net2pin_gat_attn_drop=0.0,
    ):
        super().__init__()
        self.ub_isolate = ub_isolate
        self.pin_projector = nn.Linear(pin_in_dim, hidden_dim)
        self.net_projector = nn.Linear(net_in_dim, hidden_dim)
        self.layers = nn.ModuleList([
            ThreeStageGNNLayer(
                hidden_dim,
                pin2net_type=pin2net_type,
                pin2net_gat_heads=pin2net_gat_heads,
                pin2net_gat_feat_drop=pin2net_gat_feat_drop,
                pin2net_gat_attn_drop=pin2net_gat_attn_drop,
                pin2net_gat_chunk_nets=pin2net_gat_chunk_nets,
                net2net_type=net2net_type,
                net2net_gat_heads=net2net_gat_heads,
                net2net_gat_feat_drop=net2net_gat_feat_drop,
                net2net_gat_attn_drop=net2net_gat_attn_drop,
                net2pin_type=net2pin_type,
                net2pin_gat_heads=net2pin_gat_heads,
                net2pin_gat_feat_drop=net2pin_gat_feat_drop,
                net2pin_gat_attn_drop=net2pin_gat_attn_drop,
            )
            for _ in range(n_layers)
        ])
        predictor_in_dim = hidden_dim + 1 if ub_isolate else hidden_dim
        self.predictor = nn.Sequential(
            nn.Linear(predictor_in_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, out_dim)
        )

    def encode(self, g, pin_feats, overlap_weights=None, net_feats=None):
        """
        GNN encoder: produces net embeddings h_net.
        When ub_isolate=True, h_net is purely structural; ub is applied only in the predictor.
        When ub_isolate=False, net_feats (from g) should already include ub.
        """
        h_pin = F.relu(self.pin_projector(pin_feats))
        if net_feats is None:
            net_feats = g.nodes['net'].data['feat']
        h_net = F.relu(self.net_projector(net_feats))
        for layer in self.layers:
            h_pin, h_net = layer(g, h_pin, h_net, overlap_weights)
        return h_net

    def predict_from_hnet(self, h_net, ub=None):
        """
        Prediction head. When ub_isolate=True, ub must be provided (num_nets, 1).
        When ub_isolate=False, ub is ignored.
        """
        if self.ub_isolate:
            if ub is None:
                raise ValueError("ub_isolate=True but ub was not provided")
            predictor_in = torch.cat([h_net, ub], dim=-1)
        else:
            predictor_in = h_net
        return self.predictor(predictor_in)

    def forward(self, g, pin_feats, overlap_weights=None):
        h_net = self.encode(g, pin_feats, overlap_weights)
        if self.ub_isolate:
            if 'ub' in g.nodes['net'].data:
                ub = g.nodes['net'].data['ub']
            else:
                import warnings
                warnings.warn("ub_isolate=True but 'ub' missing in graph; using ub_norm=0.5")
                ub = torch.full((h_net.shape[0], 1), 0.5, dtype=h_net.dtype, device=h_net.device)
            prediction = self.predict_from_hnet(h_net, ub=ub)
        else:
            prediction = self.predict_from_hnet(h_net)
        return prediction, h_net
