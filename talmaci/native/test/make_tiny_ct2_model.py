#!/usr/bin/env python3
"""Builds a tiny random-weight CTranslate2 model + SentencePiece tokenizer.

The output translates garbage (weights are random), but it exercises the exact
same code path in libtalmaci_native as a real OPUS-MT model: SentencePiece
load/encode/decode + CTranslate2 translate_batch. Used by the wiring smoke
test so the native library can be validated without downloading real models.

Usage: make_tiny_ct2_model.py OUTPUT_DIR
Requires: pip install ctranslate2 sentencepiece numpy
"""
import os
import random
import re
import sys
import shutil

import numpy as np
import sentencepiece as spm
from ctranslate2 import specs

DIM = 64


def train_tokenizer(out):
    corpus = os.path.join(out, "corpus.txt")
    words = ["buna", "dimineata", "astazi", "vorbim", "despre", "vreme", "good",
             "morning", "today", "we", "talk", "about", "weather", "the", "la", "si"]
    random.seed(0)
    with open(corpus, "w") as f:
        for _ in range(2000):
            f.write(" ".join(random.choices(words, k=8)) + "\n")
    spm.SentencePieceTrainer.train(input=corpus, model_prefix=os.path.join(out, "sp"),
                                   vocab_size=57, model_type="unigram", minloglevel=2)
    return os.path.join(out, "sp.model")


def resolve(obj, part):
    if hasattr(obj, part):
        return getattr(obj, part)
    m = re.fullmatch(r"(.+)_(\d+)", part)
    if m and hasattr(obj, m.group(1)):
        return getattr(obj, m.group(1))[int(m.group(2))]
    raise AttributeError(f"{type(obj).__name__} has no {part}")


def set_by_path(root, path, val):
    parts = path.split("/")
    obj = root
    for p in parts[:-1]:
        obj = resolve(obj, p)
    last = parts[-1]
    if hasattr(obj, last):
        setattr(obj, last, val)
        return
    m = re.fullmatch(r"(.+)_(\d+)", last)
    if m and hasattr(obj, m.group(1)):
        getattr(obj, m.group(1))[int(m.group(2))] = val
    else:
        setattr(obj, last, val)


def guess_shape(name, nvocab):
    n = name
    if "embeddings" in n and n.endswith("weight"):
        return (nvocab, DIM)
    if "position_encodings" in n:
        return (512, DIM)
    if "layer_norm/beta" in n or "layer_norm/gamma" in n:
        return (DIM,)
    if "projection/weight" in n:
        return (nvocab, DIM)
    if "projection/bias" in n:
        return (nvocab,)
    if "self_attention/linear_0/weight" in n:
        return (DIM * 3, DIM)
    if "attention/linear_0/weight" in n and "self_attention" not in n:
        return (DIM, DIM)
    if "self_attention/linear_1/weight" in n:
        return (DIM, DIM)
    if "attention/linear_1/weight" in n:
        return (DIM * 2, DIM)
    if "attention/linear_2/weight" in n:
        return (DIM, DIM)
    if "ffn/linear_0/weight" in n:
        return (DIM * 4, DIM)
    if "ffn/linear_0/bias" in n:
        return (DIM * 4,)
    if "ffn/linear_1/weight" in n:
        return (DIM, DIM * 4)
    if "ffn/linear_1/bias" in n:
        return (DIM,)
    if "weight" in n:
        return (DIM, DIM)
    if "bias" in n:
        return (DIM,)
    return None


def main():
    out = sys.argv[1]
    os.makedirs(os.path.join(out, "model"), exist_ok=True)
    sp_path = train_tokenizer(out)
    sp = spm.SentencePieceProcessor(model_file=sp_path)
    vocab = [sp.id_to_piece(i) for i in range(sp.get_piece_size())]

    spec = specs.TransformerSpec.from_config(num_layers=2, num_heads=2)
    rng = np.random.default_rng(0)
    for name, value in spec.variables(ordered=True):
        if value is not None:
            continue
        shape = guess_shape(name, len(vocab))
        if shape is None:
            raise RuntimeError(f"don't know a shape for {name}")
        set_by_path(spec, name, (rng.standard_normal(shape) * 0.05).astype(np.float32))

    spec.register_source_vocabulary(vocab)
    spec.register_target_vocabulary(vocab)
    spec.validate()
    model_dir = os.path.join(out, "model")
    spec.save(model_dir)
    shutil.copy(sp_path, os.path.join(model_dir, "source.spm"))
    shutil.copy(sp_path, os.path.join(model_dir, "target.spm"))
    print(model_dir)


if __name__ == "__main__":
    main()
