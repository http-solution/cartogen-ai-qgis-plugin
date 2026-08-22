# HTTP-Solution / Cartogen AI Operations Log

This private log records public-repository operations, release preparation, security documentation, and repository-boundary decisions. Do not copy this file into the public Community repository.

## 2026-08-23 — Community/private repository split and public documentation pass

### Repository boundary

- Full internal repository: `cartogenai-glitch/CARTOGEN-AI`
  - Visibility: private
  - Local source: `C:\Cartogen-AI-Core\cartogen-ai`
  - `main`: full internal tree
  - `internal-full-backup`: preserved full-tree backup
- Public Community repository: `cartogenai-glitch/cartogen_ai_community`
  - Visibility: public
  - Local source: `C:\Cartogen-AI-Core\cartogen-ai-community-limited`
  - `main`: limited Community distribution

### Public provider policy

The public Community build exposes exactly two provider choices:

1. Ollama local endpoint — no API key.
2. Cartogen AI hosted endpoint — Cartogen AI key only.

Removed from the public distribution:

- OpenRouter, Gemini, OpenAI, and Claude provider modules;
- provider-specific API-key fields and runtime selection;
- Gemini/OpenAI grounded-search tools;
- hosted billing, pricing, service, tier, and private-deployment material;
- internal product reviews, commercial roadmap documents, and private architecture notes.

The full provider and service implementation remains in this private repository.

### Public documentation published

- README branding, provider scope, installation, testing, security, and release links;
- `SECURITY.md` with implemented protections, adversarial verification, limitations,
  credential handling, and responsible disclosure guidance;
- `docs/TESTING_AND_RELEASE.md` with test commands, CI behavior, QGIS smoke-test gates,
  and release checklist;
- clean Community `CHANGELOG.md` and `metadata.txt` without commercial history;
- corrected issue templates and user guide for the two-provider public surface.

### Verification evidence

- Public limited build: 620 tests passed, 0 failures, 34 optional dependency skips.
- Python compilation passed.
- Markdown local-link scan passed with 0 broken links.
- Public provider directory contains only `ollama.py` and `cartogen.py` plus shared base/export files.
- Public tree contains no `service/`, `DOCUMENTATION.md`, tier/pricing files, or private gateway paths.
- Public `main` final commit: `bd8ee6b`.
- Full private `CARTOGEN-AI/main`: `5e4bb6f`.

### Release/security status

- Automated checks are green for the public limited build.
- Interactive QGIS smoke testing remains a release gate and must be completed in a real
  QGIS session before claiming a fully smoke-tested release.
- No credentials, tokens, or private infrastructure values were recorded in this log.
