const { pool, executeReviewOutputJob, executeBufferJob, executeIntersectionJob } = require('../server');

const POLL_MS = Number(process.env.WORKER_POLL_MS || 1000);
const ONCE = process.env.WORKER_ONCE === '1';
const WORKER_LEASE_SECONDS = Number(process.env.WORKER_LEASE_SECONDS || 300);

// Claim is a single transaction: row locking and the status transition happen
// together, so two workers can never both select the same queued job.
async function claimJob() {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await client.query(
      `SELECT id, organization_id, operation
         FROM analysis_jobs
        WHERE status = 'queued'
           OR (status = 'running' AND (output->>'lease_expires_at')::timestamptz < now())
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1`,
    );
    if (!result.rowCount) { await client.query('COMMIT'); return null; }
    const job = result.rows[0];
    const claimed = await client.query(
      `UPDATE analysis_jobs
          SET status = 'running', output = jsonb_build_object('lease_expires_at', now() + ($1 * interval '1 second'))
        WHERE id = $2 AND (status = 'queued' OR (status = 'running' AND (output->>'lease_expires_at')::timestamptz < now()))
        RETURNING id, organization_id, operation`,
      [WORKER_LEASE_SECONDS, job.id],
    );
    await client.query('COMMIT');
    return claimed.rows[0] || null;
  } catch (error) {
    try { await client.query('ROLLBACK'); } catch {}
    throw error;
  } finally { client.release(); }
}

async function executeJob(job) {
  if (job.operation === 'buffer_layer') return executeBufferJob(job.id, job.organization_id);
  if (job.operation === 'intersect_layers') return executeIntersectionJob(job.id, job.organization_id);
  if (job.operation === 'create_review_output') return executeReviewOutputJob(job.id, job.organization_id);
  throw new Error(`Unsupported analysis operation: ${job.operation}`);
}

async function tick() {
  const job = await claimJob();
  if (!job) return false;
  try {
    await executeJob(job);
    console.log(`completed ${job.operation} ${job.id}`);
  } catch (error) {
    await pool.query(`UPDATE analysis_jobs SET status = 'failed', output = $1, completed_at = now() WHERE id = $2 AND status = 'running'`, [{ error: error.message, operation: job.operation }, job.id]);
    console.error(`failed ${job.operation} ${job.id}: ${error.message}`);
  }
  return true;
}

async function main() {
  do {
    await tick();
    if (!ONCE) await new Promise(resolve => setTimeout(resolve, POLL_MS));
  } while (!ONCE);
  await pool.end();
}

if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { claimJob, executeJob, tick };
