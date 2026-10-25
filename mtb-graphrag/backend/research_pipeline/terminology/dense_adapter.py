"""Optional local SapBERT query encoder with an offline, hash-checked index.

No dependency installation, model resolution or network fetching occurs here.
The English model is a proposal generator, not a clinical identity authority.
"""
import hashlib
import json
from pathlib import Path
from .proposals import cosine


class LocalSapBERTIndex:
    supported_languages = {"en"}

    def __init__(self, manifest_path: Path, model_root: Path):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "dense-terminology-index/1.0":
            raise ValueError("Unsupported dense index schema")
        self.model_identifier = manifest["model_identifier"]
        self.model_revision = manifest["model_revision"]
        if self.model_identifier != "cambridgeltl/SapBERT-from-PubMedBERT-fulltext" or len(self.model_revision) != 40:
            raise ValueError("An explicit pinned SapBERT revision is required")
        self.index_registry_version = manifest["registry_version"]
        self.index_hash = manifest["index_hash"]
        filename = manifest["vectors_file"]
        if Path(filename).name != filename:
            raise ValueError("Invalid local vectors filename")
        data = (manifest_path.parent / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest["vectors_sha256"]:
            raise ValueError("Dense vectors hash mismatch")
        self.vectors = json.loads(data)
        # Hash all declared local model files before loading. The revision is
        # provenance metadata; content hashes are the enforced integrity check.
        for filename, digest in manifest["model_files"].items():
            target = (model_root / filename).resolve()
            if not target.is_relative_to(model_root.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("Local model hash mismatch")
        if not manifest["model_files"]:
            raise ValueError("Model file hashes are mandatory")
        from transformers import AutoModel, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_root), local_files_only=True)
        self.model = AutoModel.from_pretrained(str(model_root), local_files_only=True).eval()
        self.max_length = int(manifest["max_length"])

    def score(self, value, terms, index_hash):
        if index_hash != self.index_hash:
            raise ValueError("Dense index mismatch")
        import torch
        inputs = self.tokenizer([value], padding=True, truncation=True, max_length=self.max_length, return_tensors="pt")
        with torch.no_grad():
            query = self.model(**inputs).last_hidden_state[:, 0, :][0].tolist()
        return [cosine(query, self.vectors[t.concept_id + "\t" + t.label]) for t in terms]
