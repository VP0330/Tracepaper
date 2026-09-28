#!/usr/bin/env python
"""Phase 2a: Standalone Document Generation Test."""

import os
import sys
import json
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

# Now import
try:
    from tracepaper.ingestion import IngestionOrchestrator
    print("✓ Imported IngestionOrchestrator")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

print("\n" + "="*70)
print("PHASE 2A: DOCUMENT GENERATION WITH FULL REALISM")
print("="*70)

try:
    # Load corpus from Phase 1
    corpus_path = project_root / "corpus_data" / "corpus_full.json"
    print(f"\nLoading corpus from {corpus_path}...")
    
    if not corpus_path.exists():
        print(f"❌ Corpus file not found: {corpus_path}")
        sys.exit(1)
    
    with open(corpus_path) as f:
        corpus = json.load(f)
    
    print(f"✓ Loaded corpus with {corpus['metadata']['total_population_items']} items")
    
    # Generate all documents
    print("\nGenerating documents...")
    output_dir = project_root / "corpus_data" / "documents"
    orch = IngestionOrchestrator(seed=42, output_dir=str(output_dir))
    doc_map = orch.ingest_corpus(corpus)
    
    # Print statistics
    print("\n" + "="*70)
    print("PHASE 2A COMPLETE")
    print("="*70)
    print(f"✓ Total documents generated: {len(doc_map)}")
    print(f"✓ Documents saved to: {output_dir}")
    
    # Break down by control type
    p2p_docs = [d for d in doc_map.keys() if 'p2p_' in d]
    uar_docs = [d for d in doc_map.keys() if 'uar_' in d]
    jer_docs = [d for d in doc_map.keys() if 'jer_' in d]
    
    print(f"\nDocument Breakdown:")
    print(f"  Purchase-to-Pay: {len(p2p_docs)} documents (40 items × 3 docs)")
    print(f"  User Access Review: {len(uar_docs)} documents (40 items × 2 docs)")
    print(f"  Journal Entry Review: {len(jer_docs)} documents (40 items × 2 docs)")
    
    # Sample files
    print(f"\nSample generated files:")
    sample_files = sorted(list(doc_map.items()))[:6]
    for doc_id, path in sample_files:
        file_path = Path(path)
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"  {doc_id}: {size} bytes")
    
    print("\n" + "="*70)
    print("✅ Phase 2a document generation successful!")
    print("="*70 + "\n")
    
except Exception as e:
    print(f"\n❌ Error during document generation: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
