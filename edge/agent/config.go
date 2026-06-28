package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Config is the agent's persisted identity + server coordinates. Written
// after a successful `claim`, read on `run`.
type Config struct {
	Server        string `json:"server"`
	Token         string `json:"token"`
	DeviceID      string `json:"device_id"`
	OrgID         string `json:"org_id"`
	ProjectID     string `json:"project_id"`
	Name          string `json:"name"`
	Kind          string `json:"kind"`
	AgentVersion  string `json:"agent_version"`
	ConfigVersion string `json:"config_version,omitempty"`
}

func defaultConfigPath() string {
	if p := os.Getenv("SITEIQ_AGENT_CONFIG"); p != "" {
		return p
	}
	home, err := os.UserConfigDir()
	if err != nil {
		home = "."
	}
	return filepath.Join(home, "siteiq-agent", "config.json")
}

func loadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var c Config
	if err := json.Unmarshal(data, &c); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}
	return &c, nil
}

func saveConfig(path string, c *Config) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	// 0600: the token is a secret.
	return os.WriteFile(path, data, 0o600)
}
