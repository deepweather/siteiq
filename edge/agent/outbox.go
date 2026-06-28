package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// Envelope is the event shape the agent buffers and ships to the server.
// Mirrors EnvelopeIn in backend/api/ingest.py.
type Envelope struct {
	SubjectType   string                 `json:"subject_type"`
	SubjectID     string                 `json:"subject_id"`
	Kind          string                 `json:"kind"`
	ClientEventID string                 `json:"client_event_id"`
	OccurredAt    string                 `json:"occurred_at,omitempty"`
	Payload       map[string]interface{} `json:"payload,omitempty"`
	Confidence    float64                `json:"confidence"`
	Source        string                 `json:"source"`
	EvidenceRef   *string                `json:"evidence_ref,omitempty"`
}

// Outbox is a durable, idempotent local buffer. Construction-site links are
// flaky, so every event is persisted before we try to ship it; the server
// dedupes on client_event_id, so replay on reconnect is exactly-once.
type Outbox struct {
	db *sql.DB
}

func defaultOutboxPath() string {
	if p := os.Getenv("SITEIQ_AGENT_OUTBOX"); p != "" {
		return p
	}
	home, err := os.UserConfigDir()
	if err != nil {
		home = "."
	}
	return filepath.Join(home, "siteiq-agent", "outbox.db")
}

func openOutbox(path string) (*Outbox, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, err
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	if _, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS outbox (
			client_event_id TEXT PRIMARY KEY,
			body            TEXT NOT NULL,
			created_at      INTEGER NOT NULL
		)`); err != nil {
		return nil, err
	}
	return &Outbox{db: db}, nil
}

// Enqueue persists an event. Idempotent: a repeated client_event_id is a
// no-op (INSERT OR IGNORE).
func (o *Outbox) Enqueue(e Envelope) error {
	body, err := json.Marshal(e)
	if err != nil {
		return err
	}
	_, err = o.db.Exec(
		`INSERT OR IGNORE INTO outbox(client_event_id, body, created_at) VALUES(?,?,?)`,
		e.ClientEventID, string(body), time.Now().Unix(),
	)
	return err
}

func (o *Outbox) Depth() (int, error) {
	var n int
	err := o.db.QueryRow(`SELECT COUNT(*) FROM outbox`).Scan(&n)
	return n, err
}

// Batch returns up to `limit` oldest events.
func (o *Outbox) Batch(limit int) ([]Envelope, error) {
	rows, err := o.db.Query(
		`SELECT body FROM outbox ORDER BY created_at ASC, client_event_id ASC LIMIT ?`, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Envelope
	for rows.Next() {
		var body string
		if err := rows.Scan(&body); err != nil {
			return nil, err
		}
		var e Envelope
		if err := json.Unmarshal([]byte(body), &e); err != nil {
			return nil, fmt.Errorf("decode outbox row: %w", err)
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

// Ack removes events the server has accepted (or rejected as permanent dups).
func (o *Outbox) Ack(ids []string) error {
	if len(ids) == 0 {
		return nil
	}
	tx, err := o.db.Begin()
	if err != nil {
		return err
	}
	stmt, err := tx.Prepare(`DELETE FROM outbox WHERE client_event_id = ?`)
	if err != nil {
		_ = tx.Rollback()
		return err
	}
	defer stmt.Close()
	for _, id := range ids {
		if _, err := stmt.Exec(id); err != nil {
			_ = tx.Rollback()
			return err
		}
	}
	return tx.Commit()
}

func (o *Outbox) Close() error { return o.db.Close() }
