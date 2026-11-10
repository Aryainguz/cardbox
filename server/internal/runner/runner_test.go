package runner

import (
	"strings"
	"testing"

	"github.com/aryainguz/cardbox/server/internal/jobs"
)

func TestParseProgress(t *testing.T) {
	p, ok := ParseProgress(`@progress {"stage":"draw","done":2,"total":7}`)
	if !ok || p.Stage != "draw" || p.Done != 2 || p.Total != 7 {
		t.Fatalf("got %+v %v", p, ok)
	}
	if _, ok := ParseProgress("drawing 7 beats"); ok {
		t.Fatal("plain log lines are not progress")
	}
}

func TestReadCollectsProgressAndResult(t *testing.T) {
	in := strings.Join([]string{
		"voice: none",
		`@progress {"stage":"draw","done":1,"total":2}`,
		`@progress {"stage":"done","done":1,"total":1,"video":"/out/v.mp4","seconds":9.5}`,
	}, "\n")
	var seen []jobs.Progress
	res, tail := (&Cardbox{}).read(strings.NewReader(in), func(p jobs.Progress) { seen = append(seen, p) })
	if len(seen) != 2 || res.VideoPath != "/out/v.mp4" || res.Seconds != 9.5 || len(tail) != 1 {
		t.Fatalf("seen=%v res=%+v tail=%v", seen, res, tail)
	}
}

func TestLastLinesSkipsBlanks(t *testing.T) {
	if got := lastLines([]string{"a", "b", "", "error: bad spec", ""}, 2); got != "b | error: bad spec" {
		t.Fatalf("got %q", got)
	}
}
