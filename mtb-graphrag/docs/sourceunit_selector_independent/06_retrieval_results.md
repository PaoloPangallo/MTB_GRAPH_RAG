# Retrieval results

On 20 independent pairs and 29 directly relevant units:

- first-K HitRate@5: 0.3000; BM25: 0.3500; feature selector: 0.4500;
- first-K Recall@10: 0.2663; BM25: 0.3692; feature selector: 0.4231;
- feature selector Precision@5: 0.2000;
- feature selector MRR: 0.3417;
- mean first directly relevant rank: 1.556;
- full direct-gold coverage: 0.4000 at K=5 and 0.4000 at K=10.

The selector is strongest at moving the first relevant unit upward; full coverage remains incomplete because some documents have many relevant granular units and some GCA/document links are weak.

PMC-specific selector Recall@5 is 0.4135 and PubMed-abstract Recall@5 is 0.4167. The corpus therefore does not show collapse on long PMC documents, but the sample is still small.
