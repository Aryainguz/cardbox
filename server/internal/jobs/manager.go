package jobs

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"
)

// ErrQueueFull is returned when the backlog is at capacity (the API answers 503 with Retry-After).
var ErrQueueFull = errors.New("render queue is full")

// Result is what a successful render produced.
type Result struct {
	VideoPath string
	Seconds   float64
}

// Runner renders one job, reporting progress as it goes. It must stop promptly when ctx is canceled.
type Runner interface {
	Run(ctx context.Context, j *Job, progress func(Progress)) (Result, error)
}

// Persister is the slice of the store the manager needs.
type Persister interface {
	Update(ctx context.Context, j *Job) error
}

// Notifier is told when a job finishes (webhooks).
type Notifier interface {
	Notify(j Job)
}

// Manager runs jobs on a fixed pool of workers fed by a bounded queue.
type Manager struct {
	runner   Runner
	store    Persister
	hub      *Hub
	notifier Notifier
	log      *slog.Logger
	timeout  time.Duration

	queue   chan *Job
	wg      sync.WaitGroup
	mu      sync.Mutex
	cancels map[string]context.CancelFunc
	closed  atomic.Bool

	Running   atomic.Int64
	Completed atomic.Int64
	Failed    atomic.Int64
}

// Config sizes the pool.
type Config struct {
	Workers  int           // renders running at once (each uses a browser and ffmpeg: keep it near CPU count / 2)
	Backlog  int           // jobs waiting beyond the running ones
	Timeout  time.Duration // per-render limit
	Notifier Notifier      // optional
}

// NewManager starts `Workers` goroutines that pull from the queue until Shutdown.
func NewManager(cfg Config, runner Runner, store Persister, hub *Hub, log *slog.Logger) *Manager {
	if cfg.Workers < 1 {
		cfg.Workers = 1
	}
	if cfg.Timeout == 0 {
		cfg.Timeout = 20 * time.Minute
	}
	m := &Manager{runner: runner, store: store, hub: hub, notifier: cfg.Notifier, log: log, timeout: cfg.Timeout,
		queue: make(chan *Job, cfg.Backlog), cancels: map[string]context.CancelFunc{}}
	for i := 0; i < cfg.Workers; i++ {
		m.wg.Add(1)
		go m.worker(i)
	}
	return m
}

// Submit queues a job without blocking; it fails with ErrQueueFull when the backlog is full.
func (m *Manager) Submit(j *Job) error {
	if m.closed.Load() {
		return errors.New("shutting down")
	}
	select {
	case m.queue <- j:
		return nil
	default:
		return ErrQueueFull
	}
}

// QueueDepth is the number of jobs waiting for a worker.
func (m *Manager) QueueDepth() int { return len(m.queue) }

// Cancel stops a running job, or marks a queued one so the worker skips it. Reports whether it was found running.
func (m *Manager) Cancel(id string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	if cancel, ok := m.cancels[id]; ok {
		cancel()
		return true
	}
	m.cancels[id] = nil // tombstone: canceled before it started
	return false
}

func (m *Manager) worker(n int) {
	defer m.wg.Done()
	for j := range m.queue {
		m.run(j, n)
	}
}

func (m *Manager) save(j *Job, typ string) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := m.store.Update(ctx, j); err != nil {
		m.log.Error("saving job", "job", j.ID, "err", err)
	}
	m.hub.Publish(Event{Type: typ, Job: *j})
}

func (m *Manager) run(j *Job, worker int) {
	m.mu.Lock()
	if c, tomb := m.cancels[j.ID]; tomb && c == nil {
		delete(m.cancels, j.ID)
		m.mu.Unlock()
		m.finish(j, StatusCanceled, "canceled before it started")
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), m.timeout)
	m.cancels[j.ID] = cancel
	m.mu.Unlock()
	defer func() {
		cancel()
		m.mu.Lock()
		delete(m.cancels, j.ID)
		m.mu.Unlock()
	}()

	now := time.Now().UTC()
	j.Status, j.StartedAt = StatusRunning, &now
	m.save(j, "status")
	m.Running.Add(1)
	defer m.Running.Add(-1)
	log := m.log.With("job", j.ID, "worker", worker)
	log.Info("render started")

	res, err := m.runner.Run(ctx, j, func(p Progress) {
		j.Progress = p
		m.save(j, "progress")
	})
	switch {
	case err == nil:
		j.VideoPath, j.Seconds = res.VideoPath, res.Seconds
		m.Completed.Add(1)
		log.Info("render finished", "seconds", res.Seconds, "took", time.Since(now).Round(time.Millisecond))
		m.finish(j, StatusSucceeded, "")
	case errors.Is(ctx.Err(), context.Canceled):
		log.Info("render canceled")
		m.finish(j, StatusCanceled, "canceled")
	case errors.Is(ctx.Err(), context.DeadlineExceeded):
		m.Failed.Add(1)
		m.finish(j, StatusFailed, fmt.Sprintf("timed out after %s", m.timeout))
	default:
		m.Failed.Add(1)
		log.Warn("render failed", "err", err)
		m.finish(j, StatusFailed, err.Error())
	}
}

func (m *Manager) finish(j *Job, st Status, msg string) {
	now := time.Now().UTC()
	j.Status, j.Error, j.FinishedAt = st, msg, &now
	m.save(j, "status")
	if m.notifier != nil && j.Webhook != "" {
		m.notifier.Notify(*j)
	}
}

// Shutdown stops accepting jobs, lets running and queued renders finish until ctx expires, then cancels the rest.
func (m *Manager) Shutdown(ctx context.Context) error {
	if m.closed.Swap(true) {
		return nil
	}
	close(m.queue)
	done := make(chan struct{})
	go func() { m.wg.Wait(); close(done) }()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		m.mu.Lock()
		for _, c := range m.cancels {
			if c != nil {
				c()
			}
		}
		m.mu.Unlock()
		<-done
		return ctx.Err()
	}
}
