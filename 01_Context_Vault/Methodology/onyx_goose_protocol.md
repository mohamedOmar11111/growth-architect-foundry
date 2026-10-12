# ONYX-GOOSE PROTOCOL: Durable Automation
**Objective:** Transition from session-based tasks to durable, portable, and repeatable "Recipes."
**Inspiration:** Goose-docs.ai (Linux Foundation Agentic AI).

## 1. Mission Recipes (YAML Standard)
Every recurring strategic task (e.g., "Monthly Performance Audit", "Eid Campaign Setup") must be codified as an **Onyx Recipe**. 
*   **Location:** `04_Execution_Engine/Recipes/`
*   **Format:** YAML configuration defining specific MCP tools, persona parameters, and outcome templates.
*   **Portability:** Recipes must be executable by any agent in the Hive (Northern Wolf, Strategy Squad, etc.) regardless of the session context.

## 2. Distributed Subagent Orchestration
Move beyond monolithic responses by spawning specialized, transient subagents for high-bandwidth tasks.
*   **Research Subagent:** Handles broad web searches and documentation retrieval (using Exa/Firecrawl).
*   **Execution Subagent:** Handles direct API mutations (Google Ads, Sheets, WordPress).
*   **Audit Subagent:** Performs the "Second Pass" (Anti-AI Writing, Style Compliance).

## 3. Local-First Sensory Limbs
Prioritize local tool integration (MCP) over cloud-only interfaces to maintain data sovereignty and speed.
*   **FileSystem MCP:** Direct manipulation of the HQ structure.
*   **Memory MCP:** Long-term storage of cross-session insights in the Context Vault.
*   **Gateway MCP:** Bridging the local terminal with global LLM providers via the Onyx Gateway.

## 4. The "Goose" Sandbox Mentality
Treat complex code or data analysis tasks as sandboxed operations.
*   **Validation First:** Every automated script (e.g., `get_campaign_performance.py`) must be verified against a mock environment or a "Read-Only" first pass before full deployment.

## 5. The Graphify Layer (Cognitive Mapping)
Move from flat-file ingestion to relationship-based "Knowledge Graphs."
*   **Relationship Mapping:** Don't just read `strategy.md`. Map how it connects to `results.sheet` and `creative.png`.
*   **Token Efficiency:** Prioritize querying the "Map" over reading entire directories. Target 50x+ reduction in context usage for high-volume research.
*   **God Node Identification:** Surface the single most important design rationale or "Core Logic" that connects all client assets.

## 6. Simplicity & Surgical Impact
*   **Simplicity First:** Discard any strategic layer that doesn't produce immediate revenue.
*   **Surgical Impact:** Target only the necessary "Node" for change. Zero drive-by refactoring.
*   **Verification Cycles:** Defined success criteria (KPIs) are mandatory before any "Recipe" launch.

---
*Status: INTEGRATED | Version: 1.2 (Simplicity-Enhanced)*
