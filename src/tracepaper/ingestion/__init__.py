"""Phase 2a: Document generation utilities and orchestrator."""

from pathlib import Path
from datetime import datetime
import random
import json


class DocumentGenerator:
    """Base class for document generation."""
    
    def __init__(self, seed: int = 42, output_dir: str = "corpus_data/documents"):
        self.seed = seed
        self.output_dir = Path(output_dir)
        self.rng = random.Random(seed)
        
    def _ensure_dir(self, *parts: str) -> Path:
        """Create nested directory structure."""
        path = self.output_dir.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path


class P2PDocumentGenerator(DocumentGenerator):
    """Generate Purchase-to-Pay documents (invoices, POs, emails)."""
    
    def generate_documents(self, population_items: list) -> dict:
        """Generate P2P documents for all corpus items."""
        doc_dir = self._ensure_dir("purchase_to_pay")
        document_map = {}
        
        for pop_item in population_items:
            if pop_item["control_type"] != "purchase_to_pay":
                continue
                
            item_id = pop_item["population_item_id"]
            data = pop_item["data"]
            
            # Generate three documents per P2P item
            invoice_id = f"{item_id}_invoice"
            invoice_path = self._generate_invoice_pdf(doc_dir, invoice_id, data)
            document_map[invoice_id] = str(invoice_path)
            
            po_id = f"{item_id}_po"
            po_path = self._generate_po_csv(doc_dir, po_id, data)
            document_map[po_id] = str(po_path)
            
            approval_id = f"{item_id}_approval_email"
            approval_path = self._generate_approval_email(doc_dir, approval_id, data)
            document_map[approval_id] = str(approval_path)
        
        return document_map
    
    def _generate_invoice_pdf(self, doc_dir: Path, doc_id: str, data: dict) -> Path:
        """Generate synthetic invoice PDF (text-layer)."""
        output_path = doc_dir / f"{doc_id}.pdf"
        
        content = f"""INVOICE

Vendor: {data.get('vendor', 'Unknown Vendor')}
Vendor Email: {data.get('vendor_email', 'vendor@example.com')}

Invoice Details:
  Amount: ${data.get('amount', 0):,.2f}
  Invoice Date: {data.get('invoice_date', 'N/A')}
  PO Number: {data.get('po_number', 'N/A')}

Line Items:
  Description: Professional Services
  Quantity: 1
  Unit Price: ${data.get('amount', 0):,.2f}
  Total: ${data.get('amount', 0):,.2f}

Payment Terms: Net 30
Due Date: {data.get('invoice_date', 'N/A')}
"""
        
        output_path.write_text(f"PDF_TEXTLAYER\n{content}")
        return output_path
    
    def _generate_po_csv(self, doc_dir: Path, doc_id: str, data: dict) -> Path:
        """Generate Purchase Order CSV."""
        output_path = doc_dir / f"{doc_id}.csv"
        
        csv_content = f"""PO_NUMBER,VENDOR,AMOUNT,PO_DATE,REQUESTED_BY,APPROVER
{data.get('po_number', 'PO-000000')},{data.get('vendor', 'Unknown')},{data.get('amount', 0)},{data.get('invoice_date', 'N/A')},{data.get('requester', 'N/A')},{data.get('approver', 'N/A')}
"""
        output_path.write_text(csv_content)
        return output_path
    
    def _generate_approval_email(self, doc_dir: Path, doc_id: str, data: dict) -> Path:
        """Generate approval email."""
        output_path = doc_dir / f"{doc_id}.eml"
        
        approval_date = data.get('payment_date', 'N/A')
        
        email_content = f"""From: {data.get('requester', 'requester@company.com')}
To: {data.get('approver', 'approver@company.com')}
Subject: PO Approval - {data.get('po_number', 'PO-000000')}
Date: {approval_date}

APPROVED

Body:
I have reviewed and approved the purchase order {data.get('po_number', 'PO-000000')} for {data.get('vendor', 'Unknown Vendor')}.

Amount: ${data.get('amount', 0):,.2f}
Description: Professional Services
Approval Date: {approval_date}

Signature:
Best regards,
{data.get('requester', 'Requester Name')}
"""
        output_path.write_text(email_content)
        return output_path


class UARDocumentGenerator(DocumentGenerator):
    """Generate User Access Review documents (export CSV, memo PDF)."""
    
    def generate_documents(self, population_items: list) -> dict:
        """Generate UAR documents for all corpus items."""
        doc_dir = self._ensure_dir("user_access_review")
        document_map = {}
        
        for pop_item in population_items:
            if pop_item["control_type"] != "user_access_review":
                continue
                
            item_id = pop_item["population_item_id"]
            data = pop_item["data"]
            
            export_id = f"{item_id}_export"
            export_path = self._generate_access_export_csv(doc_dir, export_id, data)
            document_map[export_id] = str(export_path)
            
            memo_id = f"{item_id}_memo"
            memo_path = self._generate_review_memo_pdf(doc_dir, memo_id, data)
            document_map[memo_id] = str(memo_path)
        
        return document_map
    
    def _generate_access_export_csv(self, doc_dir: Path, doc_id: str, data: dict) -> Path:
        """Generate access review export CSV."""
        output_path = doc_dir / f"{doc_id}.csv"
        
        csv_content = f"""USER_ID,USERNAME,DEPARTMENT,ACTIVE,LAST_LOGIN,ACCESS_TYPE,REVIEWED_DATE
user001,john.doe,Finance,Yes,2026-09-20,SAP,{data.get('review_date', 'N/A')}
user002,jane.smith,Finance,Yes,2026-09-21,SAP,{data.get('review_date', 'N/A')}
user003,bob.johnson,Operations,No,2026-08-01,SAP,{data.get('review_date', 'N/A')}
"""
        output_path.write_text(csv_content)
        return output_path
    
    def _generate_review_memo_pdf(self, doc_dir: Path, doc_id: str, data: dict) -> Path:
        """Generate review memo PDF."""
        output_path = doc_dir / f"{doc_id}.pdf"
        
        content = f"""USER ACCESS REVIEW MEMO

Review Date: {data.get('review_date', 'N/A')}
Quarter: Q3 2026
Reviewed By: {data.get('reviewer', 'Access Manager')}

Active Users: 2
Terminated Users Identified: 1
Orphaned Access Removed: Yes

Review Findings:
  - All active users have appropriate access levels
  - Terminated user (bob.johnson) access removed
  - No segregation of duties conflicts identified

Status: Complete
Signed by Reviewer

Signature Date: {data.get('review_date', 'N/A')}
"""
        output_path.write_text(f"PDF_TEXTLAYER\n{content}")
        return output_path


class JERDocumentGenerator(DocumentGenerator):
    """Generate Journal Entry Review documents (JE CSV, explanation PDF)."""
    
    def generate_documents(self, population_items: list) -> dict:
        """Generate JER documents for all corpus items."""
        doc_dir = self._ensure_dir("journal_entry_review")
        document_map = {}
        
        for pop_item in population_items:
            if pop_item["control_type"] != "journal_entry_review":
                continue
                
            item_id = pop_item["population_item_id"]
            data = pop_item["data"]
            
            je_id = f"{item_id}_record"
            je_path = self._generate_je_csv(doc_dir, je_id, data)
            document_map[je_id] = str(je_path)
            
            exp_id = f"{item_id}_explanation"
            exp_path = self._generate_explanation_pdf(doc_dir, exp_id, data)
            document_map[exp_id] = str(exp_path)
        
        return document_map
    
    def _generate_je_csv(self, doc_dir: Path, doc_id: str, data: dict) -> Path:
        """Generate journal entry CSV."""
        output_path = doc_dir / f"{doc_id}.csv"
        
        amount = data.get('amount', 0)
        csv_content = f"""JE_ID,DATE,ACCOUNT,DESCRIPTION,DEBIT,CREDIT,PREPARER,REVIEWER
{data.get('je_number', 'JE-000001')},{data.get('posting_date', 'N/A')},5000,{data.get('description', 'JE Entry')},{amount},0,{data.get('preparer', 'N/A')},{data.get('reviewer', 'N/A')}
{data.get('je_number', 'JE-000001')},{data.get('posting_date', 'N/A')},4000,{data.get('description', 'JE Entry')},0,{amount},{data.get('preparer', 'N/A')},{data.get('reviewer', 'N/A')}
"""
        output_path.write_text(csv_content)
        return output_path
    
    def _generate_explanation_pdf(self, doc_dir: Path, doc_id: str, data: dict) -> Path:
        """Generate explanation memo PDF."""
        output_path = doc_dir / f"{doc_id}.pdf"
        
        content = f"""JOURNAL ENTRY EXPLANATION MEMO

JE ID: {data.get('je_number', 'JE-000001')}
Date: {data.get('posting_date', 'N/A')}
Amount: ${data.get('amount', 0):,.2f}

Business Purpose:
  Supporting business rationale provided
  
  {data.get('description', 'General journal entry')}

Prepared By: {data.get('preparer', 'N/A')}
Reviewed By: {data.get('reviewer', 'N/A')}
Review Date: {data.get('review_date', 'N/A')}

Approval Status: Reviewed and Approved
"""
        output_path.write_text(f"PDF_TEXTLAYER\n{content}")
        return output_path


class IngestionOrchestrator(DocumentGenerator):
    """Master orchestrator for Phase 2 document generation."""
    
    def __init__(self, seed: int = 42, output_dir: str = "corpus_data/documents"):
        super().__init__(seed, output_dir)
        self.p2p_gen = P2PDocumentGenerator(seed, output_dir)
        self.uar_gen = UARDocumentGenerator(seed, output_dir)
        self.jer_gen = JERDocumentGenerator(seed, output_dir)
    
    def ingest_corpus(self, corpus_data: dict) -> dict:
        """Ingest full corpus and generate all documents."""
        population = corpus_data['population']
        
        document_map = {}
        
        print("Generating P2P documents...")
        document_map.update(self.p2p_gen.generate_documents(population))
        
        print("Generating UAR documents...")
        document_map.update(self.uar_gen.generate_documents(population))
        
        print("Generating JER documents...")
        document_map.update(self.jer_gen.generate_documents(population))
        
        print(f"\n✓ Generated {len(document_map)} documents")
        
        self._save_manifest(document_map)
        
        return document_map
    
    def _save_manifest(self, document_map: dict) -> None:
        """Save document manifest for Phase 2b ingestion."""
        manifest_path = self.output_dir / "manifest.json"
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "total_documents": len(document_map),
            "documents": document_map,
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        print(f"✓ Manifest saved to {manifest_path}")
