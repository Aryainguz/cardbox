// Package webhook delivers job-finished callbacks, signed so receivers can verify they came from
// this server: header `Cardbox-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">`.
// Deliveries retry with exponential backoff on network errors and 5xx responses.
package webhook

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/aryainguz/cardbox/server/internal/jobs"
)

// Sender posts signed job events.
type Sender struct {
	Secret   []byte
	Client   *http.Client
	Log      *slog.Logger
	Attempts int
	Backoff  time.Duration
	BaseURL  string // public URL of this server, for links in the payload
}

// Payload is the JSON body of a webhook.
type Payload struct {
	Event    string   `json:"event"` // render.succeeded | render.failed | render.canceled
	Job      jobs.Job `json:"job"`
	VideoURL string   `json:"video_url,omitempty"`
}

// Sign returns the signature header value for a body at time t.
func Sign(secret, body []byte, t time.Time) string {
	ts := strconv.FormatInt(t.Unix(), 10)
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(ts + "."))
	mac.Write(body)
	return "t=" + ts + ",v1=" + hex.EncodeToString(mac.Sum(nil))
}

// Notify delivers in the background; it never blocks the worker that finished the job.
func (s *Sender) Notify(j jobs.Job) {
	go s.deliver(j)
}

func (s *Sender) deliver(j jobs.Job) {
	p := Payload{Event: "render." + string(j.Status), Job: j}
	if j.Status == jobs.StatusSucceeded && s.BaseURL != "" {
		p.VideoURL = s.BaseURL + "/v1/renders/" + j.ID + "/video"
	}
	body, _ := json.Marshal(p)
	attempts, backoff := max(s.Attempts, 1), s.Backoff
	if backoff == 0 {
		backoff = 2 * time.Second
	}
	for i := 0; i < attempts; i++ {
		err := s.post(j.Webhook, body)
		if err == nil {
			return
		}
		s.Log.Warn("webhook delivery failed", "job", j.ID, "attempt", i+1, "err", err)
		time.Sleep(backoff << i)
	}
}

func (s *Sender) post(url string, body []byte) error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Cardbox-Signature", Sign(s.Secret, body, time.Now()))
	resp, err := s.Client.Do(req)
	if err != nil {
		return err
	}
	resp.Body.Close()
	if resp.StatusCode >= 500 {
		return fmt.Errorf("receiver answered %d", resp.StatusCode)
	}
	return nil // 2xx-4xx: delivered (a 4xx won't get better by retrying)
}
