-- ============================================================
-- HighFold-C2C Task Parameters Table
-- ============================================================
-- This table stores parameters specific to HighFold-C2C tasks.
-- Each row links to a row in the shared `tasks` table.
-- Run this after the main init_database_postgres.sql from AstraMolecula.

CREATE TABLE IF NOT EXISTS highfold_task_params (
  id                   CHAR(32)      NOT NULL,
  task_id              CHAR(36)      NOT NULL,

  -- C2C sequence generation params
  core_sequence        VARCHAR(50)   DEFAULT NULL,
  span_len             INT           DEFAULT 5,
  num_sample           INT           DEFAULT 20,
  temperature          DECIMAL(4,2)  DEFAULT 1.0,
  top_p                DECIMAL(4,2)  DEFAULT 0.9,
  seed                 INT           DEFAULT 42,

  -- HighFold structure prediction params
  model_type           VARCHAR(50)   DEFAULT 'alphafold2',
  msa_mode             VARCHAR(50)   DEFAULT 'single_sequence',
  disulfide_bond_pairs VARCHAR(255)  DEFAULT NULL,   -- format: "2,5:3,7"
  num_models           INT           DEFAULT 5,
  num_recycle          INT           DEFAULT NULL,
  use_templates        BOOLEAN       DEFAULT FALSE,
  amber                BOOLEAN       DEFAULT FALSE,
  num_relax            INT           DEFAULT 0,

  -- Stage control
  skip_generate        BOOLEAN       DEFAULT FALSE,
  skip_predict         BOOLEAN       DEFAULT FALSE,
  skip_evaluate        BOOLEAN       DEFAULT FALSE,

  -- Timestamps
  created_at           TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
  updated_at           TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_highfold_task_params_task_id
    ON highfold_task_params(task_id);
