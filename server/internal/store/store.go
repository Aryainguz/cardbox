// Package store persists render jobs in SQLite (pure Go driver, no cgo), so jobs survive restarts
// and finished renders can be reused when the same spec is submitted again.
package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/aryainguz/cardbox/server/internal/jobs"
	_ "modernc.org/sqlite"
)

// ErrNotFound is returned when a job doesn't exist (or belongs to someone else).
var ErrNotFound = errors.New("job not found")

// Store is a SQLite-backed job store.
type Store struct{ db *sql.DB }

var migrations = []string{
	`CREATE TABLE IF NOT EXISTS jobs (
		id TEXT PRIMARY KEY,
		owner TEXT NOT NULL,
		status TEXT NOT NULL,
		spec TEXT NOT NULL,
		spec_hash TEXT NOT NULL,
		webhook TEXT NOT NULL DEFAULT '',
		stage TEXT NOT NULL DEFAULT '',
		done INTEGER NOT NULL DEFAULT 0,
		total INTEGER NOT NULL DEFAULT 0,
		error TEXT NOT NULL DEFAULT '',
		video_path TEXT NOT NULL DEFAULT '',
		seconds REAL NOT NULL DEFAULT 0,
		created_at INTEGER NOT NULL,
		started_at INTEGER,
		finished_at INTEGER
	)`,
	`CREATE INDEX IF NOT EXISTS jobs_owner_created ON jobs(owner, created_at DESC)`,
	`CREATE INDEX IF NOT EXISTS jobs_owner_hash ON jobs(owner, spec_hash, status)`,
	`CREATE TABLE IF NOT EXISTS idempotency (owner TEXT NOT NULL, key TEXT NOT NULL, job_id TEXT NOT NULL,
		PRIMARY KEY (owner, key))`,
}

// Open opens (creating if needed) the database at path and applies migrations.
func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path+"?_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)&_pragma=foreign_keys(1)")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1) // SQLite has one writer; serialising here avoids SQLITE_BUSY under load.
	for i, m := range migrations {
		if _, err := db.Exec(m); err != nil {
			return nil, fmt.Errorf("migration %d: %w", i, err)
		}
	}
	return &Store{db: db}, nil
}

// Close closes the database.
func (s *Store) Close() error { return s.db.Close() }

func unix(t *time.Time) any {
	if t == nil {
		return nil
	}
	return t.UnixMilli()
}

// Create inserts a new job.
func (s *Store) Create(ctx context.Context, j *jobs.Job) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO jobs (id, owner, status, spec, spec_hash, webhook, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)`, j.ID, j.Owner, j.Status, j.Spec, j.SpecHash, j.Webhook, j.CreatedAt.UnixMilli())
	return err
}

// Update writes a job's mutable fields.
func (s *Store) Update(ctx context.Context, j *jobs.Job) error {
	_, err := s.db.ExecContext(ctx, `UPDATE jobs SET status=?, stage=?, done=?, total=?, error=?, video_path=?, seconds=?,
		started_at=?, finished_at=? WHERE id=?`, j.Status, j.Progress.Stage, j.Progress.Done, j.Progress.Total, j.Error,
		j.VideoPath, j.Seconds, unix(j.StartedAt), unix(j.FinishedAt), j.ID)
	return err
}

const cols = `id, owner, status, spec, spec_hash, webhook, stage, done, total, error, video_path, seconds, created_at, started_at, finished_at`

func scan(row interface{ Scan(...any) error }) (*jobs.Job, error) {
	var j jobs.Job
	var created int64
	var started, finished sql.NullInt64
	if err := row.Scan(&j.ID, &j.Owner, &j.Status, &j.Spec, &j.SpecHash, &j.Webhook, &j.Progress.Stage, &j.Progress.Done,
		&j.Progress.Total, &j.Error, &j.VideoPath, &j.Seconds, &created, &started, &finished); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	j.CreatedAt = time.UnixMilli(created).UTC()
	if started.Valid {
		t := time.UnixMilli(started.Int64).UTC()
		j.StartedAt = &t
	}
	if finished.Valid {
		t := time.UnixMilli(finished.Int64).UTC()
		j.FinishedAt = &t
	}
	return &j, nil
}

// Get returns one job. With a non-empty owner, jobs of other owners are reported as not found.
func (s *Store) Get(ctx context.Context, id, owner string) (*jobs.Job, error) {
	q := `SELECT ` + cols + ` FROM jobs WHERE id = ?`
	args := []any{id}
	if owner != "" {
		q += ` AND owner = ?`
		args = append(args, owner)
	}
	return scan(s.db.QueryRowContext(ctx, q, args...))
}

// List returns an owner's jobs, newest first, created before `before` (zero time = from the newest).
func (s *Store) List(ctx context.Context, owner string, limit int, before time.Time) ([]*jobs.Job, error) {
	if before.IsZero() {
		before = time.Now().Add(time.Hour)
	}
	rows, err := s.db.QueryContext(ctx, `SELECT `+cols+` FROM jobs WHERE owner = ? AND created_at < ?
		ORDER BY created_at DESC LIMIT ?`, owner, before.UnixMilli(), limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []*jobs.Job
	for rows.Next() {
		j, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, j)
	}
	return out, rows.Err()
}

// FindSucceeded returns an owner's finished render of an identical spec, if there is one.
func (s *Store) FindSucceeded(ctx context.Context, owner, hash string) (*jobs.Job, error) {
	return scan(s.db.QueryRowContext(ctx, `SELECT `+cols+` FROM jobs WHERE owner = ? AND spec_hash = ? AND status = ?
		ORDER BY created_at DESC LIMIT 1`, owner, hash, jobs.StatusSucceeded))
}

// Unfinished returns jobs that were queued or running when the server last stopped.
func (s *Store) Unfinished(ctx context.Context) ([]*jobs.Job, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT `+cols+` FROM jobs WHERE status IN (?, ?) ORDER BY created_at`,
		jobs.StatusQueued, jobs.StatusRunning)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []*jobs.Job
	for rows.Next() {
		j, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, j)
	}
	return out, rows.Err()
}

// Remember stores an idempotency key → job mapping; it returns the existing job ID if the key was used before.
func (s *Store) Remember(ctx context.Context, owner, key, jobID string) (string, error) {
	_, err := s.db.ExecContext(ctx, `INSERT OR IGNORE INTO idempotency (owner, key, job_id) VALUES (?, ?, ?)`, owner, key, jobID)
	if err != nil {
		return "", err
	}
	var existing string
	err = s.db.QueryRowContext(ctx, `SELECT job_id FROM idempotency WHERE owner = ? AND key = ?`, owner, key).Scan(&existing)
	return existing, err
}

// Stats counts jobs by status (for /metrics).
func (s *Store) Stats(ctx context.Context) (map[jobs.Status]int, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT status, COUNT(*) FROM jobs GROUP BY status`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[jobs.Status]int{}
	for rows.Next() {
		var st jobs.Status
		var n int
		if err := rows.Scan(&st, &n); err != nil {
			return nil, err
		}
		out[st] = n
	}
	return out, rows.Err()
}
