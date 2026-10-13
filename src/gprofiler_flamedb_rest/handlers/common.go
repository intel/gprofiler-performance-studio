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
	"fmt"
	"net/http"
	"reflect"
	"strconv"
	"strings"
	"time"

	"github.com/a8m/rql"
	"github.com/gin-gonic/gin"

	"restflamedb/common"
)

func StartTime() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Set("requestStartTime", time.Now())
		c.Next()
	}
}

func parseParams[T any](params T, parser *rql.Parser, c *gin.Context) (T, common.QueryFilter, error) {
	var filterQuery common.QueryFilter
	var err error
	if err = c.ShouldBindQuery(&params); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return params, filterQuery, err
	}

	metaValue := reflect.ValueOf(&params).Elem()
	filter := metaValue.FieldByName("Filter")
	if filter.IsValid() {
		rawFilterData := []byte(filter.String())
		if len(rawFilterData) > 0 && parser != nil { // filter parameter was passed
			filterQuery, err = buildQuery(parser, rawFilterData)
			if err != nil {
				c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
				return params, filterQuery, err
			}
		}
	}

	fn := reflect.ValueOf(&params).MethodByName("CheckTimeRange")
	if fn.IsValid() {
		fn.Call(nil)
	}

	return params, filterQuery, nil
}

func buildQuery(parser *rql.Parser, rawFilterData []byte) (common.QueryFilter, error) {
	var query common.QueryFilter
	filters, err := parser.Parse(rawFilterData)
	if err != nil {
		return query, err
	}
	if filters == nil || filters.FilterExp == "" {
		return query, nil
	}

	expressions := strings.Split(filters.FilterExp, "?")
	if len(expressions) != len(filters.FilterArgs)+1 {
		return query, fmt.Errorf("filter placeholder count does not match argument count")
	}

	var clause strings.Builder
	clause.WriteString("AND ")
	for idx, expression := range expressions {
		clause.WriteString(expression)
		if idx < len(filters.FilterArgs) {
			name := "filter_" + strconv.Itoa(idx)
			clause.WriteString("@" + name)
			query.Args = append(query.Args, sql.Named(name, filters.FilterArgs[idx]))
		}
	}
	query.Clause = clause.String()
	return query, nil
}
