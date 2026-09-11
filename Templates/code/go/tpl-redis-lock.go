// Package main provides a production-ready Redis Distributed Lock implementation
// in Go using Lua script for atomic unlock and context-aware timeout.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	ErrLockNotAcquired = errors.New("redislock: lock not acquired")
	ErrLockNotHeld     = errors.New("redislock: lock not held or token mismatch")
)

const unlockLuaScript = `
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
`

type DistributedLock struct {
	client *redis.Client
	key    string
	token  string
	ttl    time.Duration
}

func randomToken() (string, error) {
	bytes := make([]byte, 16)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}

func NewDistributedLock(client *redis.Client, key string, ttl time.Duration) (*DistributedLock, error) {
	token, err := randomToken()
	if err != nil {
		return nil, fmt.Errorf("failed to generate lock token: %w", err)
	}
	return &DistributedLock{
		client: client,
		key:    key,
		token:  token,
		ttl:    ttl,
	}, nil
}

// Acquire attempts to acquire the lock atomically via SET NX PX.
func (l *DistributedLock) Acquire(ctx context.Context) error {
	ok, err := l.client.SetNX(ctx, l.key, l.token, l.ttl).Result()
	if err != nil {
		return fmt.Errorf("failed to execute SetNX: %w", err)
	}
	if !ok {
		return ErrLockNotAcquired
	}
	return nil
}

// Release releases the lock atomically via Lua script if the token matches.
func (l *DistributedLock) Release(ctx context.Context) error {
	res, err := l.client.Eval(ctx, unlockLuaScript, []string{l.key}, l.token).Result()
	if err != nil {
		return fmt.Errorf("failed to execute unlock Lua script: %w", err)
	}
	if res == int64(0) {
		return ErrLockNotHeld
	}
	return nil
}
