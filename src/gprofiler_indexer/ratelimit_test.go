//
// Copyright (C) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

package main

import (
	"testing"
	"time"
)

func TestRateLimitedWarner(t *testing.T) {
	w := newRateLimitedWarner(time.Hour)
	if !w.Warnf("first %d", 1) {
		t.Error("first warning should be logged")
	}
	if w.Warnf("second %d", 2) || w.Warnf("third %d", 3) {
		t.Error("warnings within the interval should be suppressed")
	}
	if w.suppressed != 2 {
		t.Errorf("suppressed = %d, want 2", w.suppressed)
	}

	// Once the interval has passed, the next warning is logged and the count resets.
	w.last = time.Now().Add(-2 * time.Hour)
	if !w.Warnf("fourth %d", 4) {
		t.Error("warning after the interval should be logged")
	}
	if w.suppressed != 0 {
		t.Errorf("suppressed = %d after logging, want 0", w.suppressed)
	}

	w0 := newRateLimitedWarner(0)
	if !w0.Warnf("a") || !w0.Warnf("b") {
		t.Error("with a zero interval every warning should be logged")
	}
}
