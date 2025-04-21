This prototype is a fully local, zero‑cost experiment in Retrieval‑Augmented Generation (RAG) that ingests a folder of regulatory PDFs, breaks them into paragraph‑sized chunks, embeds those chunks with the open‑source BAAI/bge‑base‑en‑v1.5 model, ranks them against a research question (expanded with GPT‑2 paraphrases), refines the shortlist with a bge‑reranker cross‑encoder, and finally weaves the top passages into a readable narrative using BART‑large‑CNN— all without touching external APIs.

Please note - files in this folder reflect work in progress
