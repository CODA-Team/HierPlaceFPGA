import os
import random

import numpy
import torch


_CHECKPOINT_CANDIDATES = (
    "last_checkpoint.pth",
    "best_checkpoint.pth",
    "best_model_graph_split.pth",
)


def checkpoint_dir(args):
    return os.path.join("../checkpoints", args.checkpoint or "default")


def resume_requested(args):
    return bool(getattr(args, "resume", False) or getattr(args, "resume_from", None))


def prepare_checkpoint_dir(args):
    if not getattr(args, "checkpoint", None):
        return None

    ckpt_dir = checkpoint_dir(args)
    if os.path.exists(ckpt_dir) and not resume_requested(args):
        raise FileExistsError(
            f"Checkpoint directory already exists: {ckpt_dir}. "
            "Use a new --checkpoint name, or pass --resume/--resume_from to continue training."
        )

    os.makedirs(ckpt_dir, exist_ok=True)
    return ckpt_dir


def _first_existing_checkpoint(path):
    for filename in _CHECKPOINT_CANDIDATES:
        candidate = os.path.join(path, filename)
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        f"No checkpoint file found in {path}. Expected one of: "
        + ", ".join(_CHECKPOINT_CANDIDATES)
    )


def resolve_resume_path(args):
    resume_from = getattr(args, "resume_from", None)
    if resume_from:
        resume_from = os.path.expanduser(resume_from)
        if os.path.isdir(resume_from):
            return _first_existing_checkpoint(resume_from)
        if not os.path.exists(resume_from):
            raise FileNotFoundError(f"--resume_from does not exist: {resume_from}")
        return resume_from

    if getattr(args, "resume", False):
        if not getattr(args, "checkpoint", None):
            raise ValueError("--resume requires --checkpoint so the checkpoint directory can be inferred.")
        return _first_existing_checkpoint(checkpoint_dir(args))

    return None


def _torch_load(path, device):
    try:
        return torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=device)


def _rng_state():
    state = {
        "python_rng_state": random.getstate(),
        "numpy_rng_state": numpy.random.get_state(),
        "torch_rng_state": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        state["cuda_rng_state_all"] = torch.cuda.get_rng_state_all()
    return state


def _as_cpu_byte_tensor(state):
    if isinstance(state, torch.Tensor):
        return state.detach().cpu().to(torch.uint8)
    return torch.as_tensor(state, dtype=torch.uint8, device="cpu")


def _restore_rng_state(checkpoint):
    if "python_rng_state" in checkpoint:
        random.setstate(checkpoint["python_rng_state"])
    if "numpy_rng_state" in checkpoint:
        numpy.random.set_state(checkpoint["numpy_rng_state"])
    if "torch_rng_state" in checkpoint:
        try:
            torch.set_rng_state(_as_cpu_byte_tensor(checkpoint["torch_rng_state"]))
        except (TypeError, RuntimeError) as exc:
            print(f"Warning: failed to restore CPU RNG state: {exc}")
    if torch.cuda.is_available() and "cuda_rng_state_all" in checkpoint:
        try:
            cuda_states = [_as_cpu_byte_tensor(s) for s in checkpoint["cuda_rng_state_all"]]
            torch.cuda.set_rng_state_all(cuda_states)
        except (TypeError, RuntimeError) as exc:
            print(f"Warning: failed to restore CUDA RNG state: {exc}")


def _atomic_torch_save(obj, path):
    tmp_path = path + ".tmp"
    torch.save(obj, tmp_path)
    os.replace(tmp_path, path)


def save_training_checkpoint(args, model, optimizer, epoch, best_val_f1, is_best=False):
    if not getattr(args, "checkpoint", None):
        return

    ckpt_dir = checkpoint_dir(args)
    os.makedirs(ckpt_dir, exist_ok=True)
    payload = {
        "epoch": int(epoch),
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "best_val_f1": float(best_val_f1),
        "args": args,
    }
    payload.update(_rng_state())

    _atomic_torch_save(payload, os.path.join(ckpt_dir, "last_checkpoint.pth"))
    if is_best:
        _atomic_torch_save(payload, os.path.join(ckpt_dir, "best_checkpoint.pth"))


def load_training_checkpoint(path, model, optimizer, device, default_best_val_f1=-1.0):
    checkpoint = _torch_load(path, device)

    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        model.load_state_dict(checkpoint["model_state_dict"])
        if "optimizer_state_dict" in checkpoint:
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        _restore_rng_state(checkpoint)

        start_epoch = int(checkpoint.get("epoch", -1)) + 1
        best_val_f1 = float(checkpoint.get("best_val_f1", default_best_val_f1))
        print(
            f"Resumed full checkpoint from {path} | "
            f"start_epoch={start_epoch} | best_val_f1={best_val_f1:.4f}"
        )
        return start_epoch, best_val_f1

    model.load_state_dict(checkpoint)
    print(
        f"Loaded model weights from {path}, but no optimizer/epoch state was found. "
        "Training will restart the optimizer from epoch 0."
    )
    return 0, default_best_val_f1
