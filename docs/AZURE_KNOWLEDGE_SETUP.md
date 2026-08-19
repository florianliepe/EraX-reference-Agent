# Azure knowledge setup

The pilot uses two isolated indexes in the existing `srch-intellectual-twin` Azure AI Search service and one private Blob container. It does not provision a graph database in phase 1. JSON-LD remains portable to a later graph store.

## Fixed pilot values

- Subscription: `25c9ce59-90a1-4e8a-a2d4-1853a19bce22`
- Resource group: `rg-ai-intellectual-twin`
- Search service: `srch-intellectual-twin`
- Evidence index: `erax-evidence-v1`
- Approved reference index: `erax-references-v1`
- Canonical language: English
- External web enrichment: disabled
- Cross-project retrieval: enabled only for claims with both `approved=true` and `reuse_allowed=true`

## Security boundary

The frontend receives no Search key, model key, or Blob SAS. Store all credentials as App Service settings. Use a managed identity and Key Vault when the dedicated resource group is available. The interim SAS must be container-scoped, HTTPS-only, write/create-only where practical, and time-limited.

## App Service settings

Configure these on `erax-reference-api-1853a19b` after the indexes and container exist:

```text
AGENTIC_WORKFLOW_ENABLED=true
CANONICAL_LANGUAGE=en
CROSS_PROJECT_REUSE_ENABLED=true
EXTERNAL_WEB_ENRICHMENT_ENABLED=false
AZURE_SEARCH_ENDPOINT=https://srch-intellectual-twin.search.windows.net
AZURE_SEARCH_API_KEY=<server-side secret>
AZURE_SEARCH_INDEX_EVIDENCE=erax-evidence-v1
AZURE_SEARCH_INDEX_REFERENCES=erax-references-v1
KNOWLEDGE_BLOB_CONTAINER_URL=https://<account>.blob.core.windows.net/knowledge?<container-sas>
```

Publication is fail-soft across optional knowledge services: an approved PowerPoint and local JSON-LD bundle are retained if Blob or Search is temporarily unavailable, and the API returns `publication.status=partial` with a diagnostic. Claim reuse remains impossible until Search publication succeeds.

## Index contracts

`erax-evidence-v1` stores immutable/normalized evidence with project, locator, classification rank, approval, reuse, language, and publication time. `erax-references-v1` stores the exact human-approved section or KPI text with its evidence IDs and source files. Both indexes must expose filterable `project_id`, `classification_rank`, `approved`, and `reuse_allowed` fields. The approved reference index must include a semantic configuration named `erax-semantic` prioritizing `content`.

The application’s query filter is:

```text
approved eq true and reuse_allowed eq true and classification_rank le <requesting-project-rank>
```

This is a pilot guard, not a substitute for user-level authorization. Entra ID group/ACL filters are required before broader rollout.
