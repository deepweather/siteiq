// SiteIQ Edge Agent — the device shell.
//
// Subcommands:
//
//	siteiq-agent claim --server <url> --code <code>   # one-time provisioning
//	siteiq-agent run   --server <url>                 # serve + flush forever
//
// `run` does three things concurrently:
//  1. exposes a LOCAL ingest endpoint (127.0.0.1) the CV sidecar and any
//     gateway bridge POST events into — the single funnel into the outbox;
//  2. flushes the durable SQLite outbox to the server with exponential
//     backoff (idempotent via client_event_id);
//  3. heartbeats + pulls config (calibration/model/sampling).
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

const agentVersion = "0.1.0"

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	switch os.Args[1] {
	case "claim":
		cmdClaim(os.Args[2:])
	case "run":
		cmdRun(os.Args[2:])
	default:
		usage()
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: siteiq-agent <claim|run> [flags]")
	os.Exit(2)
}

func cmdClaim(args []string) {
	fs := flag.NewFlagSet("claim", flag.ExitOnError)
	server := fs.String("server", "", "SiteIQ server base URL")
	code := fs.String("code", "", "one-time claim code from Settings -> Devices")
	cfgPath := fs.String("config", defaultConfigPath(), "config file path")
	_ = fs.Parse(args)
	if *server == "" || *code == "" {
		log.Fatal("claim: --server and --code are required")
	}
	cr, err := claim(*server, *code, agentVersion)
	if err != nil {
		log.Fatalf("claim failed: %v", err)
	}
	cfg := &Config{
		Server: *server, Token: cr.Token, DeviceID: cr.DeviceID,
		OrgID: cr.OrgID, ProjectID: cr.ProjectID, Name: cr.Name,
		Kind: cr.Kind, AgentVersion: agentVersion,
	}
	if err := saveConfig(*cfgPath, cfg); err != nil {
		log.Fatalf("save config: %v", err)
	}
	fmt.Printf("Claimed device %q (%s) for project %s. Config -> %s\n",
		cr.Name, cr.DeviceID, cr.ProjectID, *cfgPath)
}

func cmdRun(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	cfgPath := fs.String("config", defaultConfigPath(), "config file path")
	// Optional override of the server stored at claim time (the systemd unit
	// passes this from $SITEIQ_SERVER). Empty -> use the configured value.
	serverOverride := fs.String("server", "", "override server base URL")
	localAddr := fs.String("local-addr", "127.0.0.1:9099", "local ingest listen addr")
	flushEvery := fs.Duration("flush", 5*time.Second, "outbox flush interval")
	heartbeatEvery := fs.Duration("heartbeat", 30*time.Second, "heartbeat interval")
	batch := fs.Int("batch", 200, "max events per upload batch")
	_ = fs.Parse(args)

	cfg, err := loadConfig(*cfgPath)
	if err != nil {
		log.Fatalf("load config (run `claim` first): %v", err)
	}
	if *serverOverride != "" {
		cfg.Server = *serverOverride
	}
	outbox, err := openOutbox(defaultOutboxPath())
	if err != nil {
		log.Fatalf("open outbox: %v", err)
	}
	defer outbox.Close()
	client := newClient(cfg.Server, cfg.Token)

	// A single OS signal is delivered to exactly one channel receiver, so we
	// translate it into a CLOSED channel — closing broadcasts to every
	// goroutine waiting on `done`, stopping the flush + heartbeat loops too.
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	done := make(chan struct{})
	go func() {
		<-sig
		close(done)
	}()
	var wg sync.WaitGroup

	// 1) Local ingest server (sidecar + gateway bridges POST here).
	srv := startLocalIngest(*localAddr, outbox)

	// 2) Flush loop.
	wg.Add(1)
	go func() {
		defer wg.Done()
		flushLoop(done, client, outbox, cfg, *flushEvery, *batch)
	}()

	// 3) Heartbeat + config loop.
	wg.Add(1)
	go func() {
		defer wg.Done()
		heartbeatLoop(done, client, outbox, cfg, *cfgPath, *heartbeatEvery)
	}()

	log.Printf("siteiq-agent running: device=%s project=%s local=%s",
		cfg.DeviceID, cfg.ProjectID, *localAddr)
	<-done
	log.Println("shutting down...")
	_ = srv.Close()
	wg.Wait()
}

// startLocalIngest exposes POST /local/events accepting one or many
// EnvelopeIn objects and enqueueing them to the outbox.
func startLocalIngest(addr string, outbox *Outbox) *http.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/local/events", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}
		defer r.Body.Close()
		// Accept either a single envelope or a list.
		var list []Envelope
		dec := json.NewDecoder(r.Body)
		raw := json.RawMessage{}
		if err := dec.Decode(&raw); err != nil {
			http.Error(w, "bad json", http.StatusBadRequest)
			return
		}
		if err := json.Unmarshal(raw, &list); err != nil {
			var one Envelope
			if err2 := json.Unmarshal(raw, &one); err2 != nil {
				http.Error(w, "expected envelope or list", http.StatusBadRequest)
				return
			}
			list = []Envelope{one}
		}
		n := 0
		for _, e := range list {
			if e.ClientEventID == "" || e.SubjectID == "" || e.Kind == "" {
				continue
			}
			if e.Source == "" {
				e.Source = "sensor"
			}
			if err := outbox.Enqueue(e); err == nil {
				n++
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]int{"enqueued": n})
	})
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	})
	srv := &http.Server{Addr: addr, Handler: mux}
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("local ingest server error: %v", err)
		}
	}()
	return srv
}

func flushLoop(stop <-chan struct{}, client *Client, outbox *Outbox, cfg *Config, every time.Duration, batch int) {
	backoff := every
	const maxBackoff = 5 * time.Minute
	t := time.NewTimer(every)
	defer t.Stop()
	for {
		select {
		case <-stop:
			return
		case <-t.C:
		}
		events, err := outbox.Batch(batch)
		if err != nil {
			log.Printf("outbox read: %v", err)
			t.Reset(every)
			continue
		}
		if len(events) == 0 {
			backoff = every
			t.Reset(every)
			continue
		}
		depth, _ := outbox.Depth()
		_, err = client.SendEvents(events, cfg.AgentVersion, depth)
		if err == nil {
			ids := make([]string, len(events))
			for i, e := range events {
				ids[i] = e.ClientEventID
			}
			_ = outbox.Ack(ids)
			backoff = every
			t.Reset(every) // drain fast while backlog remains
			continue
		}
		if isPermanent(err) {
			// Malformed batch: drop it so it can't wedge the queue.
			log.Printf("dropping rejected batch: %v", err)
			ids := make([]string, len(events))
			for i, e := range events {
				ids[i] = e.ClientEventID
			}
			_ = outbox.Ack(ids)
			t.Reset(every)
			continue
		}
		// Network/5xx: back off.
		log.Printf("flush failed (will retry): %v", err)
		backoff *= 2
		if backoff > maxBackoff {
			backoff = maxBackoff
		}
		t.Reset(backoff)
	}
}

func heartbeatLoop(stop <-chan struct{}, client *Client, outbox *Outbox, cfg *Config, cfgPath string, every time.Duration) {
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-stop:
			return
		case <-t.C:
		}
		depth, _ := outbox.Depth()
		if _, err := client.Heartbeat(cfg.AgentVersion, depth); err != nil {
			log.Printf("heartbeat failed: %v", err)
			continue
		}
		// Pull config; persist the version so the sidecar can detect changes.
		if conf, err := client.Config(); err == nil {
			if v, ok := conf["config_version"].(string); ok && v != cfg.ConfigVersion {
				cfg.ConfigVersion = v
				_ = saveConfig(cfgPath, cfg)
				log.Printf("config updated -> version %s", v)
			}
		}
	}
}
