"""Engineering portfolio generation from user-uploaded files.

Deliberately isolated from `chain.py` / `rag_chain.py` / `nodes/` -- this
package imports nothing from the /ask pipeline and nothing in /ask imports
from here, so nothing here can change /ask's behavior. See
docs/portfolio.md and docs/adr/0004-portfolio-generation.md.
"""
