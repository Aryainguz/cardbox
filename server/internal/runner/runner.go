// Package runner renders jobs by running the cardbox CLI as a subprocess and translating its
// `@progress {json}` stderr lines into progress callbacks.
package runner

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/aryainguz/cardbox/server/internal/jobs"
)

const progressPrefix = "@progress "

// Cardbox runs `cardbox render` for each job in its own folder under Root.
type Cardbox struct {
	Bin  string   // path to the cardbox CLI
	Root string   // where job folders live
	Env  []string // extra environment (e.g. CARDBOX_VOICE_PYTHON)
}

type progressLine struct {
	Stage   string  `json:"stage"`
	Done    int     `json:"done"`
	Total   int     `json:"total"`
	Video   string  `json:"video"`
	Seconds float64 `json:"seconds"`
}

// ParseProgress decodes one stderr line; ok is false for ordinary log lines.
func ParseProgress(line string) (p progressLine, ok bool) {
	if !strings.HasPrefix(line, progressPrefix) {
		return p, false
	}
	return p, json.Unmarshal([]byte(strings.TrimPrefix(line, progressPrefix)), &p) == nil
}

// Run writes the spec to the job folder, renders it, and streams progress.
func (c *Cardbox) Run(ctx context.Context, j *jobs.Job, progress func(jobs.Progress)) (jobs.Result, error) {
	dir := filepath.Join(c.Root, j.ID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return jobs.Result{}, err
	}
	spec := filepath.Join(dir, "reel.yaml")
	if err := os.WriteFile(spec, []byte(j.Spec), 0o644); err != nil {
		return jobs.Result{}, err
	}
	out := filepath.Join(dir, "video.mp4")
	cmd := exec.CommandContext(ctx, c.Bin, "render", spec, "-o", out)
	cmd.Env = append(append(os.Environ(), c.Env...), "CARDBOX_PROGRESS=1", "CARDBOX_HOME="+filepath.Join(c.Root, ".home"))
	// Own process group, so cancelling also stops the browser and ffmpeg children.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return jobs.Result{}, err
	}
	if err := cmd.Start(); err != nil {
		return jobs.Result{}, fmt.Errorf("starting renderer: %w", err)
	}
	res, tail := c.read(stderr, progress)
	if err := cmd.Wait(); err != nil {
		if ctx.Err() != nil {
			return jobs.Result{}, ctx.Err()
		}
		return jobs.Result{}, fmt.Errorf("render failed: %s", lastLines(tail, 3))
	}
	if res.VideoPath == "" {
		res.VideoPath = out
	}
	if _, err := os.Stat(res.VideoPath); err != nil {
		return jobs.Result{}, errors.New("renderer finished without producing a video")
	}
	return res, nil
}

func (c *Cardbox) read(r io.Reader, progress func(jobs.Progress)) (jobs.Result, []string) {
	var res jobs.Result
	var tail []string
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 1024*1024)
	for sc.Scan() {
		line := sc.Text()
		if p, ok := ParseProgress(line); ok {
			progress(jobs.Progress{Stage: p.Stage, Done: p.Done, Total: p.Total})
			if p.Stage == "done" {
				res = jobs.Result{VideoPath: p.Video, Seconds: p.Seconds}
			}
			continue
		}
		tail = append(tail, line)
		if len(tail) > 40 {
			tail = tail[1:]
		}
	}
	return res, tail
}

func lastLines(lines []string, n int) string {
	var keep []string
	for i := len(lines) - 1; i >= 0 && len(keep) < n; i-- {
		if s := strings.TrimSpace(lines[i]); s != "" {
			keep = append([]string{s}, keep...)
		}
	}
	if len(keep) == 0 {
		return "no output"
	}
	return strings.Join(keep, " | ")
}
