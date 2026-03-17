/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
)

type JSONMap map[string]any

func ParseJSONMap(raw []byte) (JSONMap, error) {
	var parsed any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return nil, ValidationError(fmt.Sprintf("unable to parse JSON object: %v", err))
	}
	return ToJSONMap(parsed)
}

func ParseJSONStringMap(raw string) (JSONMap, error) {
	return ParseJSONMap([]byte(raw))
}

func ToJSONMap(value any) (JSONMap, error) {
	if value == nil {
		return nil, ValidationError("expected JSON object")
	}
	switch typed := value.(type) {
	case JSONMap:
		return typed, nil
	case map[string]any:
		return JSONMap(typed), nil
	default:
		data, err := json.Marshal(value)
		if err != nil {
			return nil, ValidationError("expected JSON object")
		}
		var fromMarshal any
		if err := json.Unmarshal(data, &fromMarshal); err != nil {
			return nil, ValidationError("expected JSON object")
		}
		asMap, ok := fromMarshal.(map[string]any)
		if !ok {
			return nil, ValidationError("expected JSON object")
		}
		return JSONMap(asMap), nil
	}
}

func CanonicalJSONBytes(value any) ([]byte, error) {
	var buffer bytes.Buffer
	if err := writeCanonicalJSON(&buffer, value); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}

func CanonicalJSONString(value any) (string, error) {
	bytesOut, err := CanonicalJSONBytes(value)
	if err != nil {
		return "", err
	}
	return string(bytesOut), nil
}

func writeCanonicalJSON(buffer *bytes.Buffer, value any) error {
	switch typed := value.(type) {
	case nil:
		buffer.WriteString("null")
		return nil
	case bool:
		if typed {
			buffer.WriteString("true")
		} else {
			buffer.WriteString("false")
		}
		return nil
	case string:
		encoded, _ := json.Marshal(typed)
		buffer.Write(encoded)
		return nil
	case float64:
		buffer.WriteString(strconv.FormatFloat(typed, 'g', -1, 64))
		return nil
	case float32:
		buffer.WriteString(strconv.FormatFloat(float64(typed), 'g', -1, 32))
		return nil
	case int, int8, int16, int32, int64:
		buffer.WriteString(fmt.Sprintf("%d", typed))
		return nil
	case uint, uint8, uint16, uint32, uint64:
		buffer.WriteString(fmt.Sprintf("%d", typed))
		return nil
	case json.Number:
		buffer.WriteString(typed.String())
		return nil
	case []any:
		buffer.WriteByte('[')
		for index, item := range typed {
			if index > 0 {
				buffer.WriteByte(',')
			}
			if err := writeCanonicalJSON(buffer, item); err != nil {
				return err
			}
		}
		buffer.WriteByte(']')
		return nil
	case map[string]any:
		return writeCanonicalObject(buffer, typed)
	case JSONMap:
		return writeCanonicalObject(buffer, map[string]any(typed))
	default:
		serialized, err := json.Marshal(typed)
		if err != nil {
			return ValidationError(fmt.Sprintf("unable to canonicalize JSON value: %v", err))
		}
		var reparsed any
		if err := json.Unmarshal(serialized, &reparsed); err != nil {
			return ValidationError(fmt.Sprintf("unable to canonicalize JSON value: %v", err))
		}
		return writeCanonicalJSON(buffer, reparsed)
	}
}

func writeCanonicalObject(buffer *bytes.Buffer, object map[string]any) error {
	keys := make([]string, 0, len(object))
	for key := range object {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	buffer.WriteByte('{')
	for index, key := range keys {
		if index > 0 {
			buffer.WriteByte(',')
		}
		encodedKey, _ := json.Marshal(key)
		buffer.Write(encodedKey)
		buffer.WriteByte(':')
		if err := writeCanonicalJSON(buffer, object[key]); err != nil {
			return err
		}
	}
	buffer.WriteByte('}')
	return nil
}
