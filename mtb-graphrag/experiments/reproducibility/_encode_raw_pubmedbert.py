"""Genera embedding PubMedBERT senza dipendere da path locali assoluti."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer


MODEL = "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext"


def meanpool(output, mask):
    token_embeddings = output.last_hidden_state
    expanded_mask = mask.unsqueeze(-1).float()
    return (token_embeddings * expanded_mask).sum(1) / expanded_mask.sum(1).clamp(min=1e-9)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("rag_corpus.pkl"))
    parser.add_argument("--output", type=Path, default=Path("corpus_emb_pubmedbert_raw.npy"))
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--threads", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    torch.set_num_threads(args.threads)
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL)
    model.eval()
    corpus = pd.read_pickle(args.corpus)
    texts = corpus["text"].tolist()
    embeddings = []
    started = time.time()
    with torch.no_grad():
        for start in range(0, len(texts), args.batch_size):
            batch = texts[start:start + args.batch_size]
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=args.max_length,
                return_tensors="pt",
            )
            output = model(**encoded)
            vectors = meanpool(output, encoded["attention_mask"])
            vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
            embeddings.append(vectors.cpu().numpy().astype(np.float32))
            if (start // args.batch_size) % 15 == 0:
                print(f"[{start + len(batch)}/{len(texts)}] {int(time.time() - started)}s", flush=True)
    matrix = np.vstack(embeddings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, matrix)
    print("DONE", matrix.shape, int(time.time() - started), "s", flush=True)


if __name__ == "__main__":
    main()
