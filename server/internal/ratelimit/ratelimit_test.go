package ratelimit

import (
	"testing"
	"time"
)

func TestBurstThenRefill(t *testing.T) {
	now := time.Unix(0, 0)
	l := New(60, 3) // one token a second, bursts of three
	l.now = func() time.Time { return now }
	for i := 0; i < 3; i++ {
		if ok, _ := l.Allow("k"); !ok {
			t.Fatalf("request %d should pass", i)
		}
	}
	ok, wait := l.Allow("k")
	if ok || wait <= 0 || wait > time.Second {
		t.Fatalf("4th request should wait about a second, got ok=%v wait=%v", ok, wait)
	}
	now = now.Add(1100 * time.Millisecond)
	if ok, _ := l.Allow("k"); !ok {
		t.Fatal("a token should have refilled")
	}
}

func TestKeysAreIndependent(t *testing.T) {
	l := New(60, 1)
	l.Allow("a")
	if ok, _ := l.Allow("b"); !ok {
		t.Fatal("b has its own bucket")
	}
}
