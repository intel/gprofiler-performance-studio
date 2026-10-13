//
// Copyright (C) 2023 Intel Corporation
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

package handlers

import (
	"database/sql"
	"reflect"
	"strings"
	"testing"

	"github.com/a8m/rql"
)

func TestBuildQuery(t *testing.T) {
	tests := []struct {
		arg        string
		output     string
		outputArgs []any
		parser     *rql.Parser
	}{
		{
			arg: `
				{
					  "filter": {
							"ContainerEnvName": {"$neq" : "order-router-ar"},
							"$or": [
								{"HostName": "i-052b60b314570ca6c"},
								{"HostName": "i-0dc8c3917b36b7bcb"},
								{"HostName": "i-000a551704de2f0ab"}
							]
					  }
				}
			`,
			parser: QueryParser,
			output: "AND ContainerEnvName <> @filter_0 AND (HostName = @filter_1 " +
				"OR HostName = @filter_2 OR HostName = @filter_3)",
			outputArgs: []any{
				sql.Named("filter_0", "order-router-ar"),
				sql.Named("filter_1", "i-052b60b314570ca6c"),
				sql.Named("filter_2", "i-0dc8c3917b36b7bcb"),
				sql.Named("filter_3", "i-000a551704de2f0ab"),
			},
		},
		{
			arg:    "{}",
			output: "",
			parser: QueryParser,
		},
	}
	for _, test := range tests {
		query, err := buildQuery(test.parser, []byte(test.arg))
		if err != nil {
			t.Error(err)
		}
		if query.Clause != test.output {
			t.Errorf("%v != %v", query.Clause, test.output)
		}
		if !reflect.DeepEqual(query.Args, test.outputArgs) {
			t.Errorf("%v != %v", query.Args, test.outputArgs)
		}
	}
}

func TestBuildQueryKeepsInjectionPayloadInParameter(t *testing.T) {
	payload := "x')) UNION ALL SELECT name FROM system.tables--"
	rawFilter := []byte(`{"filter":{"InstanceType":"` + payload + `"}}`)

	query, err := buildQuery(QueryParser, rawFilter)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(query.Clause, payload) || strings.Contains(query.Clause, "UNION ALL") {
		t.Fatalf("injection payload was embedded in SQL: %s", query.Clause)
	}

	expectedArgs := []any{sql.Named("filter_0", payload)}
	if !reflect.DeepEqual(query.Args, expectedArgs) {
		t.Fatalf("payload was not preserved as a query parameter: %v", query.Args)
	}
}
