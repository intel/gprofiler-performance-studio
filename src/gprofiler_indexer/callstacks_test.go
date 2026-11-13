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
	"reflect"
	"sort"
	"strings"
	"testing"
)

func TestValidExtMetrics(t *testing.T) {
	f := func(v float64) *float64 { return &v }
	longOK := strings.Repeat("a", MaxExtMetricNameLen)    // at the limit: allowed
	tooLong := strings.Repeat("a", MaxExtMetricNameLen+1) // over the limit: rejected

	valid, rejected := validExtMetrics(map[string]*float64{
		"psi.cpu.some": f(12.5),
		"psi.io.some":  f(0), // a real zero is kept
		"ext.x_1":      f(-1.5),
		"Ext/A-b 1":    f(2), // no character rules, only length
		longOK:         f(1),
		"":             f(1),
		tooLong:        f(1),
		"psi.null":     nil,      // JSON null
		"psi.huge":     f(1e39),  // outside Float32 range
		"psi.neghuge":  f(-1e39), // outside Float32 range, negative
	})

	wantValid := map[string]float32{"psi.cpu.some": 12.5, "psi.io.some": 0, "ext.x_1": -1.5, "Ext/A-b 1": 2, longOK: 1}
	if !reflect.DeepEqual(valid, wantValid) {
		t.Errorf("valid = %v, want %v", valid, wantValid)
	}
	wantRejected := []string{"", tooLong, "psi.null", "psi.huge", "psi.neghuge"}
	sort.Strings(wantRejected)
	if !reflect.DeepEqual(rejected, wantRejected) {
		t.Errorf("rejected = %q, want %q", rejected, wantRejected)
	}

	if valid, rejected := validExtMetrics(nil); len(valid) != 0 || len(rejected) != 0 {
		t.Errorf("nil map: valid = %v, rejected = %q", valid, rejected)
	}
}
