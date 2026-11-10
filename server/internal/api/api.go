// Package api is the HTTP interface of the render server.
//
//	POST   /v1/renders               submit a spec (YAML or JSON); 202 with the job
//	GET    /v1/renders               your jobs, newest first (?limit, ?before)
//	GET    /v1/renders/{id}          one job
//	GET    /v1/renders/{id}/events   live progress (Server-Sent Events)
//	GET    /v1/renders/{id}/video    the MP4 (supports Range requests)
//	DELETE /v1/renders/{id}          cancel
//	GET    /healthz, /metrics
package api

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/aryainguz/cardbox/server/internal/jobs"
	"github.com/aryainguz/cardbox/server/internal/ratelimit"
	"github.com/aryainguz/cardbox/server/internal/store"
)

const maxSpecBytes = 256 << 10

// Store is the persistence the API needs.
type Store interface {
	Create(ctx context.Context, j *jobs.Job) error
	Update(ctx context.Context, j *jobs.Job) error
	Get(ctx context.Context, id, owner string) (*jobs.Job, error)
	List(ctx context.Context, owner string, limit int, before time.Time) ([]*jobs.Job, error)
	FindSucceeded(ctx context.Context, owner, hash string) (*jobs.Job, error)
	Remember(ctx context.Context, owner, key, jobID string) (string, error)
	Stats(ctx context.Context) (map[jobs.Status]int, error)
}

// Queue is the job manager as the API sees it.
type Queue interface {
	Submit(j *jobs.Job) error
	Cancel(id string) bool
	QueueDepth() int
}

// Server wires the HTTP handlers.
type Server struct {
	Store   Store
	Queue   Queue
	Hub     *jobs.Hub
	Limiter *ratelimit.Limiter
	Log     *slog.Logger
	APIKeys map[string]string // key → owner; empty = open (local use), everyone is "local"
	Running func() int64
}

// Handler returns the routed, middleware-wrapped handler.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("GET /metrics", s.metrics)
	mux.Handle("POST /v1/renders", s.authed(s.create))
	mux.Handle("GET /v1/renders", s.authed(s.list))
	mux.Handle("GET /v1/renders/{id}", s.authed(s.get))
	mux.Handle("GET /v1/renders/{id}/events", s.authed(s.events))
	mux.Handle("GET /v1/renders/{id}/video", s.authed(s.video))
	mux.Handle("DELETE /v1/renders/{id}", s.authed(s.cancel))
	return s.requestID(s.recover(s.logRequests(mux)))
}

// ---- middleware ----

type ctxKey int

const (
	ownerKey ctxKey = iota
	reqIDKey
)

func newID(prefix string) string {
	b := make([]byte, 10)
	_, _ = rand.Read(b)
	return prefix + hex.EncodeToString(b)
}

func (s *Server) requestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-Id")
		if id == "" || len(id) > 64 {
			id = newID("req_")
		}
		w.Header().Set("X-Request-Id", id)
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), reqIDKey, id)))
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) { r.status = code; r.ResponseWriter.WriteHeader(code) }
func (r *statusRecorder) Flush() {
	if f, ok := r.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func (s *Server) logRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: 200}
		next.ServeHTTP(rec, r)
		s.Log.Info("request", "method", r.Method, "path", r.URL.Path, "status", rec.status,
			"took", time.Since(start).Round(time.Microsecond), "req", r.Context().Value(reqIDKey))
	})
}

func (s *Server) recover(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if v := recover(); v != nil {
				s.Log.Error("panic", "err", v, "path", r.URL.Path)
				writeError(w, 500, "internal_error", "something went wrong")
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// authed checks the API key (Authorization: Bearer <key>, or ?key= for <video>/<EventSource> tags that
// can't set headers) and applies the per-key rate limit.
func (s *Server) authed(h http.HandlerFunc) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		owner := "local"
		if len(s.APIKeys) > 0 {
			key := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
			if key == "" {
				key = r.URL.Query().Get("key")
			}
			owner = ""
			for k, o := range s.APIKeys {
				if subtle.ConstantTimeCompare([]byte(k), []byte(key)) == 1 {
					owner = o
				}
			}
			if owner == "" {
				writeError(w, 401, "unauthorized", "missing or invalid API key")
				return
			}
		}
		if s.Limiter != nil && r.Method != http.MethodGet {
			if ok, wait := s.Limiter.Allow(owner); !ok {
				w.Header().Set("Retry-After", strconv.Itoa(int(wait.Seconds())+1))
				writeError(w, 429, "rate_limited", "too many requests; slow down")
				return
			}
		}
		h(w, r.WithContext(context.WithValue(r.Context(), ownerKey, owner)))
	})
}

func owner(r *http.Request) string { return r.Context().Value(ownerKey).(string) }

// ---- handlers ----

type createRequest struct {
	Spec       json.RawMessage `json:"spec"`
	WebhookURL string          `json:"webhook_url"`
	Reuse      *bool           `json:"reuse"`
}

// create accepts either a raw YAML body (Content-Type: application/yaml or text/yaml) or JSON
// {"spec": "<yaml string>" | {...}, "webhook_url": "...", "reuse": true}.
func (s *Server) create(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxSpecBytes))
	if err != nil {
		writeError(w, 413, "too_large", "spec is larger than 256 KB")
		return
	}
	var req createRequest
	spec := string(body)
	if ct := r.Header.Get("Content-Type"); strings.HasPrefix(ct, "application/json") {
		if err := json.Unmarshal(body, &req); err != nil || len(req.Spec) == 0 {
			writeError(w, 400, "bad_request", `expected {"spec": ...}`)
			return
		}
		var asString string
		if json.Unmarshal(req.Spec, &asString) == nil {
			spec = asString
		} else {
			spec = string(req.Spec) // a JSON object is valid YAML
		}
	}
	if strings.TrimSpace(spec) == "" || !strings.Contains(spec, "beats") {
		writeError(w, 422, "invalid_spec", "a spec needs a title and beats (see the cardbox spec reference)")
		return
	}
	if req.WebhookURL != "" {
		if u, err := url.Parse(req.WebhookURL); err != nil || (u.Scheme != "https" && u.Scheme != "http") || u.Host == "" {
			writeError(w, 422, "invalid_webhook", "webhook_url must be an http(s) URL")
			return
		}
	}
	ctx, me := r.Context(), owner(r)
	hash := jobs.HashSpec(spec)

	// Identical spec already rendered: hand back that job instead of rendering again.
	if req.Reuse == nil || *req.Reuse {
		if done, err := s.Store.FindSucceeded(ctx, me, hash); err == nil {
			if _, statErr := os.Stat(done.VideoPath); statErr == nil {
				w.Header().Set("Cardbox-Reused", "true")
				writeJSON(w, 200, view(done))
				return
			}
		}
	}
	j := &jobs.Job{ID: newID("rnd_"), Owner: me, Status: jobs.StatusQueued, Spec: spec, SpecHash: hash,
		Webhook: req.WebhookURL, CreatedAt: time.Now().UTC()}

	// Idempotency-Key: a retried POST returns the job the first attempt created.
	if key := r.Header.Get("Idempotency-Key"); key != "" {
		existing, err := s.Store.Remember(ctx, me, key, j.ID)
		if err != nil {
			writeError(w, 500, "internal_error", "could not record idempotency key")
			return
		}
		if existing != j.ID {
			if prev, err := s.Store.Get(ctx, existing, me); err == nil {
				writeJSON(w, 200, view(prev))
				return
			}
		}
	}
	if err := s.Store.Create(ctx, j); err != nil {
		writeError(w, 500, "internal_error", "could not save the job")
		return
	}
	// Snapshot before queueing: once submitted, a worker owns *j and mutates it concurrently.
	accepted := view(j)
	if err := s.Queue.Submit(j); err != nil {
		j.Status, j.Error = jobs.StatusFailed, err.Error()
		_ = s.Store.Update(ctx, j)
		w.Header().Set("Retry-After", "30")
		writeError(w, 503, "busy", "the render queue is full; try again shortly")
		return
	}
	w.Header().Set("Location", "/v1/renders/"+j.ID)
	writeJSON(w, 202, accepted)
}

func (s *Server) list(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	var before time.Time
	if b := r.URL.Query().Get("before"); b != "" {
		if t, err := time.Parse(time.RFC3339Nano, b); err == nil {
			before = t
		}
	}
	list, err := s.Store.List(r.Context(), owner(r), limit, before)
	if err != nil {
		writeError(w, 500, "internal_error", "could not list jobs")
		return
	}
	out := make([]jobView, 0, len(list))
	for _, j := range list {
		out = append(out, view(j))
	}
	resp := map[string]any{"data": out}
	if len(list) == limit {
		resp["next_before"] = list[len(list)-1].CreatedAt.Format(time.RFC3339Nano)
	}
	writeJSON(w, 200, resp)
}

func (s *Server) load(w http.ResponseWriter, r *http.Request) (*jobs.Job, bool) {
	j, err := s.Store.Get(r.Context(), r.PathValue("id"), owner(r))
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, 404, "not_found", "no such render")
		return nil, false
	}
	if err != nil {
		writeError(w, 500, "internal_error", "could not load the job")
		return nil, false
	}
	return j, true
}

func (s *Server) get(w http.ResponseWriter, r *http.Request) {
	if j, ok := s.load(w, r); ok {
		writeJSON(w, 200, view(j))
	}
}

func (s *Server) cancel(w http.ResponseWriter, r *http.Request) {
	j, ok := s.load(w, r)
	if !ok {
		return
	}
	if j.Status.Terminal() {
		writeError(w, 409, "already_finished", "this render has already finished")
		return
	}
	s.Queue.Cancel(j.ID)
	writeJSON(w, 202, map[string]string{"id": j.ID, "status": "canceling"})
}

func (s *Server) video(w http.ResponseWriter, r *http.Request) {
	j, ok := s.load(w, r)
	if !ok {
		return
	}
	if j.Status != jobs.StatusSucceeded {
		writeError(w, 409, "not_ready", "the video isn't ready yet (status: "+string(j.Status)+")")
		return
	}
	f, err := os.Open(j.VideoPath)
	if err != nil {
		writeError(w, 410, "gone", "the video file is no longer available")
		return
	}
	defer f.Close()
	st, _ := f.Stat()
	w.Header().Set("Content-Type", "video/mp4")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`inline; filename="%s.mp4"`, j.ID))
	http.ServeContent(w, r, j.ID+".mp4", st.ModTime(), f) // handles Range, If-Modified-Since, HEAD
}

// events streams progress with Server-Sent Events until the job finishes or the client leaves.
func (s *Server) events(w http.ResponseWriter, r *http.Request) {
	j, ok := s.load(w, r)
	if !ok {
		return
	}
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, 500, "no_streaming", "streaming unsupported")
		return
	}
	ch, unsubscribe := s.Hub.Subscribe(j.ID)
	defer unsubscribe()
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Accel-Buffering", "no")
	send := func(typ string, j jobs.Job) {
		b, _ := json.Marshal(view(&j))
		fmt.Fprintf(w, "event: %s\ndata: %s\n\n", typ, b)
		flusher.Flush()
	}
	send("status", *j) // current state first, so late subscribers aren't left waiting
	if j.Status.Terminal() {
		return
	}
	ping := time.NewTicker(15 * time.Second)
	defer ping.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case <-ping.C:
			fmt.Fprint(w, ": ping\n\n")
			flusher.Flush()
		case e, open := <-ch:
			if !open {
				return
			}
			send(e.Type, e.Job)
			if e.Job.Status.Terminal() {
				return
			}
		}
	}
}

func (s *Server) metrics(w http.ResponseWriter, r *http.Request) {
	stats, err := s.Store.Stats(r.Context())
	if err != nil {
		writeError(w, 500, "internal_error", "stats unavailable")
		return
	}
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	fmt.Fprintln(w, "# HELP cardbox_jobs Jobs by status.\n# TYPE cardbox_jobs gauge")
	for _, st := range []jobs.Status{jobs.StatusQueued, jobs.StatusRunning, jobs.StatusSucceeded, jobs.StatusFailed, jobs.StatusCanceled} {
		fmt.Fprintf(w, "cardbox_jobs{status=%q} %d\n", st, stats[st])
	}
	fmt.Fprintf(w, "# HELP cardbox_queue_depth Jobs waiting for a worker.\n# TYPE cardbox_queue_depth gauge\ncardbox_queue_depth %d\n", s.Queue.QueueDepth())
	if s.Running != nil {
		fmt.Fprintf(w, "# HELP cardbox_renders_running Renders in progress.\n# TYPE cardbox_renders_running gauge\ncardbox_renders_running %d\n", s.Running())
	}
}

// ---- responses ----

type jobView struct {
	jobs.Job
	VideoURL  string `json:"video_url,omitempty"`
	EventsURL string `json:"events_url"`
}

func view(j *jobs.Job) jobView {
	v := jobView{Job: *j, EventsURL: "/v1/renders/" + j.ID + "/events"}
	if j.Status == jobs.StatusSucceeded {
		v.VideoURL = "/v1/renders/" + j.ID + "/video"
	}
	return v
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, code int, kind, msg string) {
	writeJSON(w, code, map[string]map[string]string{"error": {"type": kind, "message": msg}})
}
