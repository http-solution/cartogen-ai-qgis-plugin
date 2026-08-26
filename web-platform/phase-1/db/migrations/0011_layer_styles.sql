-- Persisted organization/project-scoped layer presentation metadata.
ALTER TABLE project_layers
  ADD COLUMN IF NOT EXISTS style_preset text NOT NULL DEFAULT 'coverage',
  ADD COLUMN IF NOT EXISTS style_color text NOT NULL DEFAULT '#d96a54',
  ADD COLUMN IF NOT EXISTS style_fill_opacity numeric NOT NULL DEFAULT 55,
  ADD COLUMN IF NOT EXISTS style_line_weight numeric NOT NULL DEFAULT 2,
  ADD COLUMN IF NOT EXISTS style_classification text NOT NULL DEFAULT 'DRAFT · REVIEW REQUIRED',
  ADD COLUMN IF NOT EXISTS style_legend_label text;
