# HyperCutNet: Net Cut Connectivity Prediction

This project implements a **multi-stage Heterogeneous Graph Neural Network (GNN)** to predict the connectivity or cut probability of nets in graphs for circuit partitioning.

## Key Features

*   **Heterogeneous Graph Modeling**: Constructs a DGL graph with `Pin` and `Net` nodes:
    *   `Pin -> Net` edges (membership)
    *   `Net -> Pin` edges (feedback)
    *   `Net <-> Net` edges (weighted overlap)
*   **3-Stage Sequential GNN**:
    1.  **Upload**: Nets aggregate features from connected Pins.
    2.  **Propagate**: Nets exchange information with neighboring Nets (weighted by overlap count).
    3.  **Feedback**: Pins update their states based on the refined Net embeddings.
*   **Pin Features**: Base features from `nodes.txt` + clustering coefficient + 2nd-order degree + optional node2vec + optional PageRank.
*   **Net Features**: Net size (number of pins).
*   **Training**: BCEWithLogitsLoss; evaluation via precision, recall, F1-score.
*   **Optional**: Save per-design prediction files (`net_id cut_or_not` per line).

## Structure

```
.
├── rawdata/                       # Root directory for graph data
│   ├── design_A/
│   │   ├── nodes.txt              # Pin features
│   │   └── hedges.txt             # Net connectivity & labels
│   └── ...
├── src/
│   ├── parser.py                  # Data parser, structural features, node2vec, PageRank
│   ├── model.py                   # GNN architecture (NetPredictor)
│   ├── train.py                   # Training, evaluation, prediction output
│   └── args.py                    # CLI arguments
├── environment.yml
└── README.md
```

## Installation

Requires **PyTorch**, **DGL**, **NetworkX**, and **scikit-learn**. Optional: **node2vec** (for `--use_node2vec`).

### Option 1: Conda

1.  **Clone the repository**
    ```bash
    git clone https://github.com/your-username/ML-SpecPart.git
    cd ML-SpecPart
    ```

2.  **Create the environment**
    You can create the environment using the provided `environment.yml`. This setup defaults to **CUDA 12.1**.
    ```bash
    conda env create -f environment.yml
    conda activate gnn_design
    ```

### Option 2: Manual Install

If you prefer pip or use a different CUDA version (e.g., CPU-only or CUDA 11.8), follow these steps:

1.  **Install PyTorch**
    Check [pytorch.org](https://pytorch.org/get-started/locally/) for your specific version.
    ```bash
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    ```

2.  **Install DGL**
    Check [dgl.ai](https://www.dgl.ai/pages/start.html) for your specific version.
    ```bash
    pip install dgl -f https://data.dgl.ai/wheels/cu121/repo.html
    ```

3.  **Install other dependencies**
    ```bash
    pip install numpy scipy tqdm
    ```

## 🏃‍♂️ Usage

### 1. Prepare Data

Each design folder (e.g., `rawdata/design_A/`) should contain:

*   **`nodes.txt`**: Each line contains node features:
    ```text
    node_id weight in_degree out_degree
    ```
*   **`hedges.txt`**: Each line contains net information and the target label:
    ```text
    net_id; pin_id_1 pin_id_2 ...; label
    ```
    *Note: The `label` is the regression target (e.g., connectivity or cut probability).*

### 2. Run Training
Run the training script from the **root** directory of the project. The script automatically handles graph construction, batching, and dataset splitting.
You can use --dataset\_savepath to save/read the constructed graphs, avoiding building the graphs from scrach everytime.

```bash
python src/train.py --data_root ../rawdata --dataset_savepath ../dataset --checkpoint run1 --batch_size 4 --layers 3 --hidden_dim 128 --epochs 200 --lr 0.001
```

### 3. Optional Flags

| Flag | Description |
|------|-------------|
| `--use_node2vec` | Append node2vec embeddings (64-d by default) as pin features. Requires `node2vec` package. |
| `--use_pagerank` | Append PageRank scores as pin features. |
| `--save_predictions` | Write per-design prediction files to `checkpoints/<name>/predictions/<design>.txt` (each line: `net_id cut`). |

**Example with all options:**

```bash
python src/train.py --data_root ./rawdata --checkpoint full_run \
  --use_node2vec --use_pagerank --save_predictions \
  --batch_size 4 --epochs 200
```

### 4. Output

*   Logs and best model: `../checkpoints/<checkpoint>/`
*   With `--save_predictions`: `../checkpoints/<checkpoint>/predictions/<design>.txt`
