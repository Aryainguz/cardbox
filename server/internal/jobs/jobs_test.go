package jobs

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"
)

type memStore struct {
	mu   sync.Mutex
	last map[string]Job
}

func (m *memStore) Update(_ context.Context, j *Job) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.last == nil {
		m.last = map[string]Job{}
	}
	m.last[j.ID] = *j
	return nil
}

func (m *memStore) get(id string) Job {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.last[id]
}

type fakeRunner struct {
	block chan struct{}
	fail  bool
}

func (f *fakeRunner) Run(ctx context.Context, j *Job, progress func(Progress)) (Result, error) {
	progress(Progress{Stage: "draw", Done: 1, Total: 2})
	if f.block != nil {
		select {
		case <-f.block:
		case <-ctx.Done():
			return Result{}, ctx.Err()
		}
	}
	if f.fail {
		return Result{}, errors.New("boom")
	}
	return Result{VideoPath: "/tmp/x.mp4", Seconds: 12.5}, nil
}

func quiet() *slog.Logger { return slog.New(slog.NewTextHandler(io.Discard, nil)) }

func waitFor(t *testing.T, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for !cond() {
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting")
		}
		time.Sleep(5 * time.Millisecond)
	}
}

func TestJobSucceedsAndPublishesEvents(t *testing.T) {
	st, hub := &memStore{}, NewHub()
	m := NewManager(Config{Workers: 1, Backlog: 4}, &fakeRunner{}, st, hub, quiet())
	defer m.Shutdown(context.Background())
	j := &Job{ID: "a", Status: StatusQueued}
	events, unsub := hub.Subscribe("a")
	defer unsub()
	if err := m.Submit(j); err != nil {
		t.Fatal(err)
	}
	var seen []string
	for e := range events {
		seen = append(seen, string(e.Job.Status)+":"+e.Type)
		if e.Job.Status.Terminal() {
			break
		}
	}
	if got := st.get("a"); got.Status != StatusSucceeded || got.Seconds != 12.5 || got.FinishedAt == nil {
		t.Fatalf("unexpected final job: %+v", got)
	}
	if seen[0] != "running:status" || seen[len(seen)-1] != "succeeded:status" {
		t.Fatalf("unexpected event order: %v", seen)
	}
}

func TestFailureIsRecorded(t *testing.T) {
	st := &memStore{}
	m := NewManager(Config{Workers: 1, Backlog: 1}, &fakeRunner{fail: true}, st, NewHub(), quiet())
	_ = m.Submit(&Job{ID: "f"})
	waitFor(t, func() bool { return st.get("f").Status == StatusFailed })
	if st.get("f").Error != "boom" || m.Failed.Load() != 1 {
		t.Fatalf("failure not recorded: %+v", st.get("f"))
	}
	_ = m.Shutdown(context.Background())
}

func TestCancelRunningJob(t *testing.T) {
	st, r := &memStore{}, &fakeRunner{block: make(chan struct{})}
	m := NewManager(Config{Workers: 1, Backlog: 1}, r, st, NewHub(), quiet())
	_ = m.Submit(&Job{ID: "c"})
	waitFor(t, func() bool { return st.get("c").Status == StatusRunning })
	if !m.Cancel("c") {
		t.Fatal("expected the job to be running")
	}
	waitFor(t, func() bool { return st.get("c").Status == StatusCanceled })
	_ = m.Shutdown(context.Background())
}

func TestCancelQueuedJobSkipsIt(t *testing.T) {
	st, r := &memStore{}, &fakeRunner{block: make(chan struct{})}
	m := NewManager(Config{Workers: 1, Backlog: 2}, r, st, NewHub(), quiet())
	_ = m.Submit(&Job{ID: "first"})
	waitFor(t, func() bool { return st.get("first").Status == StatusRunning })
	_ = m.Submit(&Job{ID: "second"})
	m.Cancel("second")
	close(r.block)
	waitFor(t, func() bool { return st.get("second").Status == StatusCanceled })
	_ = m.Shutdown(context.Background())
}

func TestQueueFull(t *testing.T) {
	r := &fakeRunner{block: make(chan struct{})}
	st := &memStore{}
	m := NewManager(Config{Workers: 1, Backlog: 1}, r, st, NewHub(), quiet())
	_ = m.Submit(&Job{ID: "1"})
	waitFor(t, func() bool { return st.get("1").Status == StatusRunning })
	_ = m.Submit(&Job{ID: "2"})
	if err := m.Submit(&Job{ID: "3"}); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("want ErrQueueFull, got %v", err)
	}
	close(r.block)
	_ = m.Shutdown(context.Background())
}

func TestShutdownCancelsAfterGrace(t *testing.T) {
	st, r := &memStore{}, &fakeRunner{block: make(chan struct{})}
	m := NewManager(Config{Workers: 1, Backlog: 1}, r, st, NewHub(), quiet())
	_ = m.Submit(&Job{ID: "s"})
	waitFor(t, func() bool { return st.get("s").Status == StatusRunning })
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if err := m.Shutdown(ctx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("want deadline exceeded, got %v", err)
	}
	if st.get("s").Status != StatusCanceled {
		t.Fatalf("running job should be canceled, got %s", st.get("s").Status)
	}
}

func TestHubDropsOldestForSlowSubscribers(t *testing.T) {
	h := NewHub()
	ch, unsub := h.Subscribe("x")
	for i := 0; i < 100; i++ {
		h.Publish(Event{Type: "progress", Job: Job{ID: "x", Progress: Progress{Done: i}}})
	}
	var last Event
	for len(ch) > 0 {
		last = <-ch
	}
	if last.Job.Progress.Done != 99 {
		t.Fatalf("newest event should survive, got %d", last.Job.Progress.Done)
	}
	unsub()
	if h.Subscribers("x") != 0 {
		t.Fatal("unsubscribe should remove the subscriber")
	}
}
