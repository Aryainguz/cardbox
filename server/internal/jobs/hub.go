package jobs

import "sync"

// Event is one update about a job, sent to every subscriber of that job.
type Event struct {
	Type string `json:"type"` // "progress" or "status"
	Job  Job    `json:"job"`
}

// Hub fans job events out to subscribers. Slow subscribers never block the publisher: each has a
// small buffer, and if it fills up, the oldest pending event is dropped in favour of the newest
// (progress is a "latest value wins" stream).
type Hub struct {
	mu   sync.Mutex
	subs map[string]map[chan Event]struct{}
}

// NewHub returns an empty hub.
func NewHub() *Hub { return &Hub{subs: map[string]map[chan Event]struct{}{}} }

// Subscribe returns a channel of events for one job and a function that unsubscribes.
func (h *Hub) Subscribe(jobID string) (<-chan Event, func()) {
	ch := make(chan Event, 16)
	h.mu.Lock()
	if h.subs[jobID] == nil {
		h.subs[jobID] = map[chan Event]struct{}{}
	}
	h.subs[jobID][ch] = struct{}{}
	h.mu.Unlock()
	return ch, func() {
		h.mu.Lock()
		defer h.mu.Unlock()
		if _, ok := h.subs[jobID][ch]; ok {
			delete(h.subs[jobID], ch)
			close(ch)
			if len(h.subs[jobID]) == 0 {
				delete(h.subs, jobID)
			}
		}
	}
}

// Publish sends an event to every subscriber of its job without blocking.
func (h *Hub) Publish(e Event) {
	h.mu.Lock()
	defer h.mu.Unlock()
	for ch := range h.subs[e.Job.ID] {
		select {
		case ch <- e:
		default:
			select { // full: drop the oldest event, keep the newest
			case <-ch:
			default:
			}
			select {
			case ch <- e:
			default:
			}
		}
	}
}

// Subscribers counts live subscribers of a job (for tests and metrics).
func (h *Hub) Subscribers(jobID string) int {
	h.mu.Lock()
	defer h.mu.Unlock()
	return len(h.subs[jobID])
}
