const { pool, executeReviewOutputJob, executeBufferJob, executeIntersectionJob } = require('../server');

const POLL_MS = Number(process.env.WORKER_POLL_MS || 1000);
const ONCE = process.env.WORKER_ONCE === '1';

async function claimJob() {
  const result = await pool.query(
    `SELECT id, organization_id, operation
       FROM analysis_jobs
      WHERE status = 'queued'
      ORDER BY created_at
      LIMIT 1`,
  );
  if (!result.rowCount) return null;
  const job = result.rows[0];
  const lock = await pool.query('SELECT pg_try_advisory_lock(hashtext($1)) AS claimed', [String(job.id)]);
  if (!lock.rows[0].claimed) return null;
  return job;
}

async function executeJob(job) {
  if (job.operation === 'buffer_layer') return executeBufferJob(job.id, job.organization_id);
  if (job.operation === 'intersect_layers') return executeIntersectionJob(job.id, job.organization_id);
  return executeReviewOutputJob(job.id, job.organization_id);
}

async function tick() {
  const job = await claimJob();
  if (!job) return false;
  try {
    await executeJob(job);
    console.log(`completed ${job.operation} ${job.id}`);
  } catch (error) {
    await pool.query(
      `UPDATE analysis_jobs SET status = 'failed', output = $1, completed_at = now() WHERE id = $2`,
      [{ error: error.message, operation: job.operation }, job.id],
    );
    console.error(`failed ${job.operation} ${job.id}: ${error.message}`);
  } finally {
    await pool.query('SELECT pg_advisory_unlock(hashtext($1))', [String(job.id)]);
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
