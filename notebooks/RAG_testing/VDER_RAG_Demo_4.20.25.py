# -*- coding: utf-8 -*-
"""
RAG and Summarization Script based on VDER_RAG_Demo_4.20.25.ipynb

Purpose:
1. Reads PDF documents from a specified directory.
2. Extracts text paragraphs (chunks) from the PDFs.
3. Takes a user question and finds the most relevant text chunks using:
    - Query paraphrasing (using GPT-2).
    - Dense vector embeddings (BAAI/bge-base-en-v1.5).
    - Re-ranking with a cross-encoder (BAAI/bge-reranker-base).
4. Saves the ranked text chunks (RAG hits) to a CSV file.
5. Attempts to generate a narrative summary of the top-ranked chunks using
   a Map-Reduce approach with a summarization model (facebook/bart-large-cnn).
6. Prints the final summary.

Setup:
1. Save this code as a Python file (e.g., `rag_summarizer.py`).
2. Make sure you have Python 3 installed.
3. Place the PDF documents you want to analyze into a single folder.
4. Edit the CONFIG section below, especially:
    - `PDF_DIR`: Set this to the full path of the folder containing your PDFs.
    - `QUESTION`: Set this to the question you want to ask about the documents.
    - `OUT_CSV`: The filename for the saved RAG hits.
    - Other parameters (like TOP_K, PARAPHRASE_K, summarization settings) can be adjusted if needed.

Running the Script:
1. Open a terminal or command prompt.
2. Navigate to the directory where you saved this script.
3. Run the script using: python rag_summarizer.py
4. The script will install missing dependencies if necessary (requires internet connection).
5. It will then process the PDFs, perform RAG, save the CSV, attempt summarization, and print the results.
   Note: Processing PDFs and downloading models can take time, especially on the first run.

Dependencies (will be installed automatically if missing):
- pdfplumber
- sentence-transformers
- transformers (including PyTorch or TensorFlow backend)
- pandas
- tqdm
- torch (or tensorflow)
"""

# ───────────────── CONFIG ───────────────────────────────────────────────────────
# --- RAG Configuration ---
PDF_DIR = r"C:\Users\" # !!! IMPORTANT: SET THIS PATH !!!
QUESTION = "What are current best practices to determining the value of distributed energy?" # The question to ask
TOP_K = 20              # Final number of results to retrieve and save
PARAPHRASE_K = 4        # How many extra query variants (plus original) for dense retrieval
OUT_CSV = "rag_hits_v2.csv" # Output CSV file for ranked chunks

DENSE_MODEL = "BAAI/bge-base-en-v1.5"     # Model for initial dense retrieval
CROSS_MODEL = "BAAI/bge-reranker-base"  # Model for re-ranking

# --- Summarization Configuration ---
SUMMARIZE_RESULTS = True  # Set to False to skip the summarization step
SUMMARIZER_MODEL = "facebook/bart-large-cnn"
SUMM_TOP_N = 10           # How many top RAG hits to use for summarization input
SUMM_CHUNKS_PER_BATCH = 2 # How many chunks to summarize in each 'map' step (adjust based on token limits)
# ────────────────────────────────────────────────────────────────────────────────

# -- 0. Dependency bootstrap & Imports -------------------------------------------
import subprocess
import sys
import importlib.metadata as im
import logging
import os
from pathlib import Path
from typing import List, Tuple
from math import ceil
import warnings

# Check and install missing packages
REQ = ["pdfplumber", "sentence-transformers", "transformers", "pandas", "tqdm", "torch"] # Added torch requirement explicitly
try:
    # Check if tensorflow is installed as an alternative backend for transformers
    im.distribution("tensorflow")
    if "torch" in REQ: REQ.remove("torch") # Remove torch if tensorflow is present
except im.PackageNotFoundError:
    pass # Tensorflow not found, torch requirement remains if it was there

missing = []
for p in REQ:
    try:
        im.distribution(p)
    except im.PackageNotFoundError:
        # Handle cases where package name differs from import name (like sentence-transformers)
        if p == "sentence-transformers":
             try: im.distribution("sentence_transformers")
             except im.PackageNotFoundError: missing.append(p)
        elif p == "torch":
             try: im.distribution("torch")
             except im.PackageNotFoundError: missing.append(p)
        else:
            missing.append(p)


if missing:
    print(f"🔧 Installing missing packages: {', '.join(missing)}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *missing])
        print("✅ Installation complete.")
        # Re-import after installation if needed, or just proceed
        print("🔄 Re-running imports after installation...")
        importlib.invalidate_caches() # Ensure new packages are found
    except Exception as e:
        print(f"❌ Error installing packages: {e}")
        print("Please install the required packages manually: pip install pdfplumber sentence-transformers transformers pandas tqdm torch")
        sys.exit(1)

# Proceed with imports
import torch
import pdfplumber
import pandas as pd
from tqdm import tqdm
from transformers import pipeline, AutoTokenizer
from sentence_transformers import SentenceTransformer, CrossEncoder, util

# Suppress specific warnings if needed
logging.getLogger("pypdf").setLevel(logging.ERROR) # Mute CropBox chatter
warnings.filterwarnings("ignore", message="Your input sequence length.*") # Optional: Mute length warnings if they become noisy

# Determine device (CPU or CUDA GPU)
device_type = "cuda" if torch.cuda.is_available() else "cpu"
print(f"⚙️ Using device: {device_type}")
# For pipeline device: 0 for cuda, -1 for cpu
pipeline_device = 0 if device_type == "cuda" else -1

# -- 1. PDF Handling Functions ----------------------------------------------------
def extract_paragraphs(pdf_path: Path) -> List[Tuple[str, str]]:
    """Return (paragraph_text, 'filename pX') tuples, filtering <200 chars."""
    out: List[Tuple[str, str]] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for pg, page in enumerate(pdf.pages, start=1):
                txt = page.extract_text(x_tolerance=2, y_tolerance=2) or "" # Added tolerance
                # Simple paragraph split logic (adjust if needed based on PDF structure)
                # This splits on double newlines OR single newlines preceded by punctuation/lowercase.
                paragraphs = []
                current_para = ""
                lines = txt.split('\n')
                for i, line in enumerate(lines):
                    line = line.strip()
                    if not line: # Empty line likely paragraph break
                        if current_para:
                            paragraphs.append(current_para)
                        current_para = ""
                    else:
                         # Add space if concatenating lines within a paragraph
                        if current_para:
                            current_para += " " + line
                        else:
                            current_para = line
                if current_para: # Add last paragraph
                    paragraphs.append(current_para)

                for para in paragraphs:
                    clean = para.strip()
                    if len(clean) >= 200: # Keep paragraph length filter
                        out.append((clean, f"{pdf_path.name}  p{pg}"))
    except Exception as e:
        print(f"⚠️ Error processing {pdf_path.name}: {e}")
    return out

def build_corpus(folder: Path) -> Tuple[List[str], List[str]]:
    """Builds lists of texts and their corresponding labels (sources) from PDFs."""
    texts, labels = [], []
    pdf_files = list(folder.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ No PDF files found in directory: {folder}")
        return [], []
    print(f"🔎 Found {len(pdf_files)} PDF files.")
    for p in tqdm(pdf_files, desc="📚 Reading PDFs"):
        chunks = extract_paragraphs(p)
        if chunks:
            t, l = zip(*chunks)
            texts.extend(t)
            labels.extend(l)
    return texts, labels

# -- 2. RAG Retrieval + Re-ranking Function ---------------------------------------
def rank_chunks_plus(
    texts: list[str],
    labels: list[str],
    question: str,
    top_k: int = 20,
    paraphrase_k: int = 4, # Note: total variants = paraphrase_k + 1
    dense_model_name: str = DENSE_MODEL,
    cross_model_name: str = CROSS_MODEL,
) -> pd.DataFrame:
    """Dense retrieve → cross‑rerank; return DataFrame of top‑k chunks."""
    print(f"🧠 Initializing Dense model: {dense_model_name}")
    dense = SentenceTransformer(dense_model_name, device=device_type)

    # 2.1 Generate query paraphrases (very light GPT-2; completely offline)
    print(f"✍️ Generating {paraphrase_k} paraphrases for the question...")
    try:
        # Use device=-1 (CPU) for paraphrasing as it's lightweight
        llm = pipeline("text-generation", model="gpt2", device=-1, verbose=False)
        prompts = [f"Paraphrase: {question}"] * paraphrase_k
        variants = [
            llm(p, max_new_tokens=30, num_return_sequences=1, do_sample=False)[0]["generated_text"]
            .split("Paraphrase:")[-1].strip()
            for p in prompts
        ]
        variants.append(question) # Add the original question
        # Filter out empty strings just in case
        variants = [v for v in variants if v]
        print(f"⇢ Using {len(variants)} query variants.")
    except Exception as e:
        print(f"⚠️ Warning: Failed to generate paraphrases using GPT-2 ({e}). Using only the original question.")
        variants = [question]

    # 2.2 Dense Embedding and Retrieval
    print(f"📊 Encoding {len(texts)} text chunks...")
    q_vec = dense.encode(variants).mean(axis=0) # Calculate centroid vector for query
    emb_t = dense.encode(texts, batch_size=128, show_progress_bar=True) # Increase batch size if memory allows
    print("✨ Calculating similarities...")
    sims = util.cos_sim(q_vec, emb_t)[0].cpu().tolist()

    # Create initial DataFrame and get top N*5 for re-ranking
    coarse_df = pd.DataFrame({"report_name": labels, "section": texts, "similarity": sims})
    # Handle case where fewer chunks exist than top_k * 5
    num_coarse_candidates = min(len(coarse_df), top_k * 5)
    coarse_candidates = coarse_df.nlargest(num_coarse_candidates, "similarity").reset_index(drop=True)
    print(f"🏅 Top {num_coarse_candidates} candidates after dense retrieval:")
    print(coarse_candidates[['report_name', 'similarity']].head())

    # 2.3 Cross-Encoder Re-ranking
    if cross_model_name and not coarse_candidates.empty:
        print(f"\n🧠 Initializing Cross-Encoder model: {cross_model_name}")
        cross_encoder = CrossEncoder(cross_model_name, device=device_type, max_length=512) # Set max_length
        print("✨ Re-ranking candidates...")
        pairs = [(question, t) for t in coarse_candidates["section"]]
        rerank_scores = cross_encoder.predict(pairs, show_progress_bar=True)
        coarse_candidates["rerank_score"] = rerank_scores
        # Sort by re-rank score and select top_k
        final_df = coarse_candidates.nlargest(top_k, "rerank_score").drop(columns=["rerank_score"])
        print(f"🏅 Top {top_k} candidates after re-ranking:")
        # Rename 'similarity' to 'rerank_score' or keep both? Keep dense 'similarity'.
        print(final_df[['report_name', 'similarity']].head())

    elif not coarse_candidates.empty:
        print("ℹ️ Skipping Re-ranking step as CROSS_MODEL is not specified.")
        # If no re-ranking, just take the top_k from dense results
        final_df = coarse_candidates.head(top_k)
    else:
        print("⚠️ No candidates found after dense retrieval. Cannot re-rank.")
        final_df = coarse_candidates # Return empty DataFrame

    return final_df.reset_index(drop=True)

# -- 3. Summarization Function (Map-Reduce) --------------------------------------
def summarize_map_reduce(
    texts_to_summarize: List[str],
    summarizer_pipeline,
    tokenizer,
    model_max_len: int,
    chunks_per_batch: int = 2,
    max_len_intermediate: int = 150,
    min_len_intermediate: int = 30,
    max_len_final: int = 350,
    min_len_final: int = 75
) -> str:
    """Generates a summary using the Map-Reduce technique."""

    if not texts_to_summarize:
        return "[No text provided for summarization]"

    num_chunks = len(texts_to_summarize)
    num_batches = ceil(num_chunks / chunks_per_batch)
    intermediate_summaries = []
    failed_batches = 0

    print(f"\n🔄 Starting Summarization Map phase: Summarizing {num_chunks} chunks in {num_batches} batches...")
    for i in tqdm(range(num_batches), desc="🗺️ Map Phase"):
        start_index = i * chunks_per_batch
        end_index = start_index + chunks_per_batch
        batch_texts = texts_to_summarize[start_index:end_index]
        batch_combined = "\n\n".join(batch_texts)

        # Check token count for the batch
        try:
             batch_token_count = len(tokenizer.encode(batch_combined))
             print(f"  Batch {i+1}/{num_batches}, Input Token Count: {batch_token_count}")
             if batch_token_count > model_max_len:
                 print(f"  ⚠️ WARNING: Batch {i+1} input ({batch_token_count} tokens) exceeds model limit ({model_max_len}). Truncation will occur.")
        except Exception as e:
             print(f"  ⚠️ Warning: Could not check token count for batch {i+1}: {e}")
             batch_token_count = model_max_len # Assume it might exceed

        try:
            # Summarize this small batch
            batch_summary_result = summarizer_pipeline(
                batch_combined,
                max_length=max_len_intermediate,
                min_length=min_len_intermediate,
                truncation=True, # Crucial for batches potentially exceeding limit
                do_sample=False
            )
            intermediate_summaries.append(batch_summary_result[0]['summary_text'])
            # print(f"  Batch {i+1} intermediate summary generated.")
        except Exception as e:
            # *** Gracefully handle errors during batch summarization ***
            print(f"  ❌ ERROR summarizing batch {i+1}: {e}")
            print(f"     Skipping batch {i+1}. Input may be too complex or malformed even after truncation.")
            intermediate_summaries.append(f"[Error summarizing batch {i+1}: Text may be too complex.]") # Placeholder
            failed_batches += 1

    if not intermediate_summaries or all("[Error summarizing" in s for s in intermediate_summaries):
         return "[Summarization failed for all batches]"

    print(f"\n🔄 Starting Summarization Reduce phase (Summarized {num_batches - failed_batches}/{num_batches} batches)...")
    combined_intermediate_summary = "\n\n".join(intermediate_summaries)

    # Check token count for the combined intermediate summaries
    try:
        final_input_token_count = len(tokenizer.encode(combined_intermediate_summary))
        print(f"  Token count for final summary input: {final_input_token_count}")
        if final_input_token_count > model_max_len:
            print(f"  ⚠️ WARNING: Combined intermediate summaries ({final_input_token_count} tokens) might be too long ({model_max_len}). Truncation will occur.")
    except Exception as e:
         print(f"  ⚠️ Warning: Could not check token count for final input: {e}")

    try:
        # Final summary generation
        final_summary_result = summarizer_pipeline(
            combined_intermediate_summary,
            max_length=max_len_final,
            min_length=min_len_final,
            truncation=True, # Truncate combined summary if needed
            do_sample=False
        )
        final_narrative = final_summary_result[0]['summary_text']
        print("✅ Final summary generated.")
    except Exception as e:
        print(f"❌ Error during final summarization (Reduce phase): {e}")
        final_narrative = f"[Error during final summarization phase: {e}]"
        # Optionally return the combined intermediate summaries if final fails
        # final_narrative += "\n\nCombined Intermediate Summaries:\n" + combined_intermediate_summary

    return final_narrative


# -- 4. Main Orchestration Function -----------------------------------------------
def main():
    """Main function to run the RAG and Summarization pipeline."""
    root = Path(PDF_DIR).expanduser()
    if not root.is_dir():
        print(f"❌ Error: PDF directory not found or is not a directory: {root}")
        sys.exit(1)

    # --- RAG Pipeline ---
    print("\n▶ Building corpus...")
    texts, labels = build_corpus(root)
    if not texts:
        print("❌ No text chunks extracted from PDFs. Please check the PDF files and directory.")
        sys.exit(1)
    print(f"✅ {len(texts):,} text chunks extracted.")

    print("\n▶ Running RAG pipeline (Retrieval + Re-ranking)...")
    rag_df = rank_chunks_plus(
        texts, labels, QUESTION,
        top_k=TOP_K,
        paraphrase_k=PARAPHRASE_K,
        dense_model_name=DENSE_MODEL,
        cross_model_name=CROSS_MODEL
    )

    if rag_df.empty:
        print("\n❌ RAG pipeline returned no results.")
    else:
        print(f"\n✅ RAG pipeline complete. Top {len(rag_df)} results:")
        # Display top 5 hits for confirmation
        print(rag_df.head().to_string())

        if OUT_CSV:
            try:
                rag_df.to_csv(OUT_CSV, index=False, encoding='utf-8')
                print(f"\n💾 Ranked results saved to: {OUT_CSV}")
            except Exception as e:
                print(f"❌ Error saving results to CSV: {e}")

    # --- Summarization Pipeline (Optional) ---
    if SUMMARIZE_RESULTS and not rag_df.empty:
        print(f"\n▶ Initializing Summarization Model ({SUMMARIZER_MODEL})...")
        try:
            summarizer_tokenizer = AutoTokenizer.from_pretrained(SUMMARIZER_MODEL)
            summarizer = pipeline("summarization", model=SUMMARIZER_MODEL, tokenizer=summarizer_tokenizer, device=pipeline_device)
            # Get model's actual max length, default to 1024 if unavailable
            summ_model_max_len = getattr(summarizer.model.config, 'max_position_embeddings', 1024)
            print(f"  Summarizer initialized. Model max input length: {summ_model_max_len} tokens.")

            # Select top N sections from RAG results for summarization
            sections_to_summarize = rag_df.head(SUMM_TOP_N)['section'].tolist()
            sources_for_summary = rag_df.head(SUMM_TOP_N)['report_name'].tolist()

            narrative_summary = summarize_map_reduce(
                sections_to_summarize,
                summarizer,
                summarizer_tokenizer,
                summ_model_max_len,
                chunks_per_batch=SUMM_CHUNKS_PER_BATCH
            )

            print("\n" + "="*80)
            print("📝 FINAL NARRATIVE SUMMARY")
            print("="*80)
            # Use textwrap for cleaner printing
            import textwrap
            print(textwrap.fill(narrative_summary, width=100))
            print("-" * 80)
            print("Sources contributing to the summary:")
            for i, src in enumerate(sources_for_summary):
                print(f"  [{i+1}] {src}")
            print("="*80)

        except Exception as e:
            print(f"\n❌ An error occurred during the summarization setup or process: {e}")
            print("Skipping summarization.")
    elif SUMMARIZE_RESULTS and rag_df.empty:
        print("\nℹ️ Skipping summarization because RAG returned no results.")
    else:
        print("\nℹ️ Summarization is disabled (SUMMARIZE_RESULTS=False).")


if __name__ == "__main__":
    print("🚀 Starting RAG & Summarization Script...")
    main()
    print("\n🏁 Script finished.")
