// cardbox-server: an HTTP render service for cardbox. Submit a spec, follow progress live, download
// the video. Configured with environment variables (see README).
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/aryainguz/cardbox/server/internal/api"
	"github.com/aryainguz/cardbox/server/internal/jobs"
	"github.com/aryainguz/cardbox/server/internal/ratelimit"
	"github.com/aryainguz/cardbox/server/internal/runner"
	"github.com/aryainguz/cardbox/server/internal/store"
	"github.com/aryainguz/cardbox/server/internal/webhook"
)

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if n, err := strconv.Atoi(os.Getenv(key)); err == nil {
		return n
	}
	return def
}

// parseKeys reads CARDBOX_API_KEYS="key1:alice,key2:bob" (owner defaults to the key's position).
func parseKeys(s string) map[string]string {
	out := map[string]string{}
	for i, part := range strings.Split(s, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		key, who, ok := strings.Cut(part, ":")
		if !ok {
			who = "key" + strconv.Itoa(i+1)
		}
		out[key] = who
	}
	return out
}

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	data := env("CARDBOX_DATA", "./data")
	if err := os.MkdirAll(filepath.Join(data, "renders"), 0o755); err != nil {
		log.Error("data dir", "err", err)
		os.Exit(1)
	}
	st, err := store.Open(filepath.Join(data, "cardbox.db"))
	if err != nil {
		log.Error("opening database", "err", err)
		os.Exit(1)
	}
	defer st.Close()

	hub := jobs.NewHub()
	sender := &webhook.Sender{Secret: []byte(env("CARDBOX_WEBHOOK_SECRET", "change-me")), Client: &http.Client{Timeout: 15 * time.Second},
		Log: log, Attempts: 5, BaseURL: env("CARDBOX_PUBLIC_URL", "")}
	run := &runner.Cardbox{Bin: env("CARDBOX_BIN", "cardbox"), Root: filepath.Join(data, "renders")}
	if vp := os.Getenv("CARDBOX_VOICE_PYTHON"); vp != "" {
		run.Env = append(run.Env, "CARDBOX_VOICE_PYTHON="+vp)
	}
	mgr := jobs.NewManager(jobs.Config{
		Workers:  envInt("CARDBOX_WORKERS", 2),
		Backlog:  envInt("CARDBOX_BACKLOG", 64),
		Timeout:  time.Duration(envInt("CARDBOX_RENDER_TIMEOUT_MIN", 20)) * time.Minute,
		Notifier: sender,
	}, run, st, hub, log)

	// Jobs left queued or running by a previous process are queued again.
	if left, err := st.Unfinished(context.Background()); err == nil {
		for _, j := range left {
			j.Status = jobs.StatusQueued
			_ = st.Update(context.Background(), j)
			if err := mgr.Submit(j); err != nil {
				log.Warn("could not requeue", "job", j.ID, "err", err)
			}
		}
		if len(left) > 0 {
			log.Info("requeued unfinished jobs", "count", len(left))
		}
	}

	srv := &api.Server{Store: st, Queue: mgr, Hub: hub, Log: log, APIKeys: parseKeys(os.Getenv("CARDBOX_API_KEYS")),
		Limiter: ratelimit.New(envInt("CARDBOX_RATE_PER_MIN", 30), envInt("CARDBOX_RATE_BURST", 10)),
		Running: mgr.Running.Load}
	httpSrv := &http.Server{Addr: env("CARDBOX_ADDR", ":8080"), Handler: srv.Handler(), ReadHeaderTimeout: 10 * time.Second}

	go func() {
		log.Info("listening", "addr", httpSrv.Addr, "auth", len(srv.APIKeys) > 0)
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("server", "err", err)
			os.Exit(1)
		}
	}()

	stop, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	<-stop.Done()
	log.Info("shutting down: finishing running renders")
	ctx, done := context.WithTimeout(context.Background(), time.Duration(envInt("CARDBOX_SHUTDOWN_GRACE_SEC", 60))*time.Second)
	defer done()
	_ = httpSrv.Shutdown(ctx)
	if err := mgr.Shutdown(ctx); err != nil {
		log.Warn("shutdown grace expired; canceled the rest", "err", err)
	}
	log.Info("bye")
}
