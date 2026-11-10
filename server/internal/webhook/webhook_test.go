package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/aryainguz/cardbox/server/internal/jobs"
)

func TestSignatureVerifies(t *testing.T) {
	secret, body := []byte("s3cret"), []byte(`{"a":1}`)
	sig := Sign(secret, body, time.Unix(1700000000, 0))
	ts, v1, _ := strings.Cut(strings.TrimPrefix(sig, "t="), ",v1=")
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(ts + "." + string(body)))
	if v1 != hex.EncodeToString(mac.Sum(nil)) || ts != "1700000000" {
		t.Fatalf("bad signature %q", sig)
	}
}

func TestDeliveryRetriesOn5xx(t *testing.T) {
	var calls atomic.Int32
	got := make(chan Payload, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if calls.Add(1) < 3 {
			w.WriteHeader(503)
			return
		}
		if !strings.HasPrefix(r.Header.Get("Cardbox-Signature"), "t=") {
			t.Error("missing signature")
		}
		var p Payload
		_ = json.NewDecoder(r.Body).Decode(&p)
		got <- p
	}))
	defer srv.Close()
	s := &Sender{Secret: []byte("x"), Client: srv.Client(), Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
		Attempts: 4, Backoff: time.Millisecond, BaseURL: "https://api.example"}
	s.Notify(jobs.Job{ID: "rnd_1", Status: jobs.StatusSucceeded, Webhook: srv.URL})
	select {
	case p := <-got:
		if p.Event != "render.succeeded" || p.VideoURL != "https://api.example/v1/renders/rnd_1/video" {
			t.Fatalf("unexpected payload %+v", p)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("webhook never delivered")
	}
}
