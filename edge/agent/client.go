package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Client talks to the SiteIQ server's device ingestion surface.
type Client struct {
	server string
	token  string
	http   *http.Client
}

func newClient(server, token string) *Client {
	return &Client{
		server: server,
		token:  token,
		http:   &http.Client{Timeout: 30 * time.Second},
	}
}

type claimResponse struct {
	DeviceID  string `json:"device_id"`
	Token     string `json:"token"`
	OrgID     string `json:"org_id"`
	ProjectID string `json:"project_id"`
	Name      string `json:"name"`
	Kind      string `json:"kind"`
}

// Claim exchanges a one-time code for a device token (no token yet).
func claim(server, code, agentVersion string) (*claimResponse, error) {
	body, _ := json.Marshal(map[string]string{"code": code, "agent_version": agentVersion})
	req, _ := http.NewRequest(http.MethodPost, server+"/api/ingest/claim", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{Timeout: 30 * time.Second}).Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("claim failed (%d): %s", resp.StatusCode, string(data))
	}
	var cr claimResponse
	if err := json.Unmarshal(data, &cr); err != nil {
		return nil, err
	}
	return &cr, nil
}

func (c *Client) do(method, path string, body interface{}) (*http.Response, error) {
	var rdr io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, c.server+path, rdr)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	return c.http.Do(req)
}

type eventsResult struct {
	Accepted   int `json:"accepted"`
	Duplicates int `json:"duplicates"`
	Received   int `json:"received"`
}

// SendEvents ships a batch. A 2xx means the server staged (or deduped) every
// event, so the whole batch can be acked. A 4xx (other than 401) means the
// batch is malformed and will never succeed — caller drops it. Network/5xx
// errors are retried.
func (c *Client) SendEvents(events []Envelope, agentVersion string, queueDepth int) (*eventsResult, error) {
	resp, err := c.do(http.MethodPost, "/api/ingest/events", map[string]interface{}{
		"events":        events,
		"agent_version": agentVersion,
		"queue_depth":   queueDepth,
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode == http.StatusUnauthorized {
		return nil, fmt.Errorf("unauthorized: device token rejected")
	}
	if resp.StatusCode >= 400 && resp.StatusCode < 500 {
		return nil, &permanentError{fmt.Sprintf("rejected (%d): %s", resp.StatusCode, string(data))}
	}
	if resp.StatusCode >= 500 {
		return nil, fmt.Errorf("server error (%d)", resp.StatusCode)
	}
	var r eventsResult
	_ = json.Unmarshal(data, &r)
	return &r, nil
}

func (c *Client) Heartbeat(agentVersion string, queueDepth int) (map[string]interface{}, error) {
	resp, err := c.do(http.MethodPost, "/api/ingest/heartbeat", map[string]interface{}{
		"agent_version": agentVersion,
		"queue_depth":   queueDepth,
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var out map[string]interface{}
	data, _ := io.ReadAll(resp.Body)
	_ = json.Unmarshal(data, &out)
	return out, nil
}

func (c *Client) Config() (map[string]interface{}, error) {
	resp, err := c.do(http.MethodGet, "/api/ingest/config", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var out map[string]interface{}
	data, _ := io.ReadAll(resp.Body)
	_ = json.Unmarshal(data, &out)
	return out, nil
}

// permanentError marks a batch the server rejected with a 4xx — retrying it
// is pointless, so the flush loop drops it.
type permanentError struct{ msg string }

func (e *permanentError) Error() string { return e.msg }

func isPermanent(err error) bool {
	_, ok := err.(*permanentError)
	return ok
}
