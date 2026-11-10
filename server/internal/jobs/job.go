// Package jobs holds the render job model, the job queue with its worker pool, and the progress hub
// that fans progress events out to subscribers (Server-Sent Events clients).
package jobs

import (
	"crypto/sha256"
	"encoding/hex"
	"time"
)

// Status is where a job is in its lifecycle: queued → running → succeeded | failed | canceled.
type Status string

const (
	StatusQueued    Status = "queued"
	StatusRunning   Status = "running"
	StatusSucceeded Status = "succeeded"
	StatusFailed    Status = "failed"
	StatusCanceled  Status = "canceled"
)

// Terminal reports whether a job in this status will never change again.
func (s Status) Terminal() bool {
	return s == StatusSucceeded || s == StatusFailed || s == StatusCanceled
}

// Progress is the latest progress event a renderer reported.
type Progress struct {
	Stage string `json:"stage"`
	Done  int    `json:"done"`
	Total int    `json:"total"`
}

// Job is one render request.
type Job struct {
	ID         string     `json:"id"`
	Owner      string     `json:"-"`
	Status     Status     `json:"status"`
	Spec       string     `json:"-"`
	SpecHash   string     `json:"spec_hash"`
	Webhook    string     `json:"webhook_url,omitempty"`
	Progress   Progress   `json:"progress"`
	Error      string     `json:"error,omitempty"`
	VideoPath  string     `json:"-"`
	Seconds    float64    `json:"seconds,omitempty"`
	CreatedAt  time.Time  `json:"created_at"`
	StartedAt  *time.Time `json:"started_at,omitempty"`
	FinishedAt *time.Time `json:"finished_at,omitempty"`
}

// HashSpec is a stable content hash of a spec, used to reuse identical renders.
func HashSpec(spec string) string {
	sum := sha256.Sum256([]byte(spec))
	return hex.EncodeToString(sum[:])
}
