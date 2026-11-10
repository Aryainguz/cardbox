package api

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/aryainguz/cardbox/server/internal/jobs"
	"github.com/aryainguz/cardbox/server/internal/ratelimit"
	"github.com/aryainguz/cardbox/server/internal/store"
)

const spec = "title: Test\nvoice: none\nbeats:\n  - {kind: end, text: Bye, say: Bye.}\n"

// fakeRunner "renders" by writing a few bytes, after reporting progress.
type fakeRunner struct{ dir string }

func (f fakeRunner) Run(ctx context.Context, j *jobs.Job, progress func(jobs.Progress)) (jobs.Result, error) {
	progress(jobs.Progress{Stage: "draw", Done: 1, Total: 1})
	time.Sleep(30 * time.Millisecond)
	out := filepath.Join(f.dir, j.ID+".mp4")
	if err := os.WriteFile(out, []byte("not really an mp4"), 0o644); err != nil {
		return jobs.Result{}, err
	}
	return jobs.Result{VideoPath: out, Seconds: 3}, nil
}

func setup(t *testing.T, keys map[string]string) (*httptest.Server, func()) {
	t.Helper()
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hub := jobs.NewHub()
	mgr := jobs.NewManager(jobs.Config{Workers: 2, Backlog: 8}, fakeRunner{dir}, st, hub, log)
	s := &Server{Store: st, Queue: mgr, Hub: hub, Log: log, APIKeys: keys, Limiter: ratelimit.New(600, 100)}
	ts := httptest.NewServer(s.Handler())
	return ts, func() { ts.Close(); _ = mgr.Shutdown(context.Background()); st.Close() }
}

func do(t *testing.T, method, url, body string, hdr map[string]string) (*http.Response, map[string]any) {
	t.Helper()
	req, _ := http.NewRequest(method, url, strings.NewReader(body))
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return resp, out
}

func waitStatus(t *testing.T, base, id string, want jobs.Status) map[string]any {
	t.Helper()
	for i := 0; i < 200; i++ {
		_, j := do(t, "GET", base+"/v1/renders/"+id, "", nil)
		if j["status"] == string(want) {
			return j
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("job %s never reached %s", id, want)
	return nil
}

func TestRenderLifecycle(t *testing.T) {
	ts, done := setup(t, nil)
	defer done()
	resp, j := do(t, "POST", ts.URL+"/v1/renders", spec, map[string]string{"Content-Type": "application/yaml"})
	if resp.StatusCode != 202 || j["status"] != "queued" || resp.Header.Get("Location") == "" {
		t.Fatalf("create: %d %v", resp.StatusCode, j)
	}
	id := j["id"].(string)
	final := waitStatus(t, ts.URL, id, jobs.StatusSucceeded)
	if final["video_url"] != "/v1/renders/"+id+"/video" {
		t.Fatalf("missing video url: %v", final)
	}
	vr, err := http.Get(ts.URL + "/v1/renders/" + id + "/video")
	if err != nil || vr.StatusCode != 200 || vr.Header.Get("Content-Type") != "video/mp4" {
		t.Fatalf("video: %v %v", err, vr.StatusCode)
	}
	vr.Body.Close()
	// A range request gets partial content.
	req, _ := http.NewRequest("GET", ts.URL+"/v1/renders/"+id+"/video", nil)
	req.Header.Set("Range", "bytes=0-3")
	pr, _ := http.DefaultClient.Do(req)
	b, _ := io.ReadAll(pr.Body)
	pr.Body.Close()
	if pr.StatusCode != 206 || string(b) != "not " {
		t.Fatalf("range: %d %q", pr.StatusCode, b)
	}
}

func TestJSONBodyAndReuse(t *testing.T) {
	ts, done := setup(t, nil)
	defer done()
	body, _ := json.Marshal(map[string]any{"spec": spec})
	_, j := do(t, "POST", ts.URL+"/v1/renders", string(body), map[string]string{"Content-Type": "application/json"})
	waitStatus(t, ts.URL, j["id"].(string), jobs.StatusSucceeded)
	resp, again := do(t, "POST", ts.URL+"/v1/renders", string(body), map[string]string{"Content-Type": "application/json"})
	if resp.StatusCode != 200 || resp.Header.Get("Cardbox-Reused") != "true" || again["id"] != j["id"] {
		t.Fatalf("identical spec should reuse the finished render: %d %v", resp.StatusCode, again)
	}
}

func TestIdempotencyKey(t *testing.T) {
	ts, done := setup(t, nil)
	defer done()
	h := map[string]string{"Content-Type": "application/yaml", "Idempotency-Key": "abc"}
	_, first := do(t, "POST", ts.URL+"/v1/renders", spec+"# 1\n", h)
	_, second := do(t, "POST", ts.URL+"/v1/renders", spec+"# 2\n", h)
	if first["id"] != second["id"] {
		t.Fatalf("same idempotency key should return the same job: %v vs %v", first["id"], second["id"])
	}
}

func TestEventsStreamUntilDone(t *testing.T) {
	ts, done := setup(t, nil)
	defer done()
	_, j := do(t, "POST", ts.URL+"/v1/renders", spec+"# sse\n", map[string]string{"Content-Type": "application/yaml"})
	resp, err := http.Get(ts.URL + "/v1/renders/" + j["id"].(string) + "/events")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.Header.Get("Content-Type") != "text/event-stream" {
		t.Fatalf("content type %q", resp.Header.Get("Content-Type"))
	}
	var events []string
	sc := bufio.NewScanner(resp.Body)
	for sc.Scan() {
		if line := sc.Text(); strings.HasPrefix(line, "data: ") {
			var v map[string]any
			_ = json.Unmarshal([]byte(line[6:]), &v)
			events = append(events, v["status"].(string))
		}
	}
	if len(events) < 2 || events[len(events)-1] != "succeeded" {
		t.Fatalf("stream should end with succeeded, got %v", events)
	}
}

func TestAuthAndOwnership(t *testing.T) {
	ts, done := setup(t, map[string]string{"k-alice": "alice", "k-bob": "bob"})
	defer done()
	if resp, _ := do(t, "POST", ts.URL+"/v1/renders", spec, nil); resp.StatusCode != 401 {
		t.Fatalf("no key should be 401, got %d", resp.StatusCode)
	}
	_, j := do(t, "POST", ts.URL+"/v1/renders", spec, map[string]string{"Authorization": "Bearer k-alice"})
	if resp, _ := do(t, "GET", ts.URL+"/v1/renders/"+j["id"].(string), "", map[string]string{"Authorization": "Bearer k-bob"}); resp.StatusCode != 404 {
		t.Fatalf("bob must not see alice's job, got %d", resp.StatusCode)
	}
}

func TestValidation(t *testing.T) {
	ts, done := setup(t, nil)
	defer done()
	if resp, _ := do(t, "POST", ts.URL+"/v1/renders", "hello", nil); resp.StatusCode != 422 {
		t.Fatalf("not a spec should be 422, got %d", resp.StatusCode)
	}
	body := `{"spec": "beats: []", "webhook_url": "ftp://x"}`
	if resp, _ := do(t, "POST", ts.URL+"/v1/renders", body, map[string]string{"Content-Type": "application/json"}); resp.StatusCode != 422 {
		t.Fatalf("bad webhook should be 422, got %d", resp.StatusCode)
	}
	if resp, _ := do(t, "GET", ts.URL+"/v1/renders/nope", "", nil); resp.StatusCode != 404 {
		t.Fatalf("unknown id should be 404, got %d", resp.StatusCode)
	}
}

func TestMetrics(t *testing.T) {
	ts, done := setup(t, nil)
	defer done()
	resp, err := http.Get(ts.URL + "/metrics")
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if !strings.Contains(string(b), `cardbox_jobs{status="succeeded"}`) || !strings.Contains(string(b), "cardbox_queue_depth") {
		t.Fatalf("metrics missing series:\n%s", b)
	}
}
