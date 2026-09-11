// Package main provides a resident Worker Pool template
// with buffered channel, graceful cancellation, and task tracking.
package main

import (
	"context"
	"fmt"
	"sync"
	"time"
)

type Task struct {
	ID      string
	Payload string
}

type WorkerPool struct {
	workerCount int
	taskQueue   chan Task
	wg          sync.WaitGroup
}

func NewWorkerPool(workerCount, queueSize int) *WorkerPool {
	return &WorkerPool{
		workerCount: workerCount,
		taskQueue:   make(chan Task, queueSize),
	}
}

func (p *WorkerPool) Start(ctx context.Context) {
	for i := 1; i <= p.workerCount; i++ {
		p.wg.Add(1)
		go p.worker(ctx, i)
	}
}

func (p *WorkerPool) worker(ctx context.Context, id int) {
	defer p.wg.Done()
	for {
		select {
		case <-ctx.Done():
			fmt.Printf("Worker %d exiting on context cancellation\n", id)
			return
		case task, ok := <-p.taskQueue:
			if !ok {
				fmt.Printf("Worker %d task channel closed, exiting\n", id)
				return
			}
			p.process(id, task)
		}
	}
}

func (p *WorkerPool) process(workerID int, task Task) {
	fmt.Printf("[Worker %d] Processing task %s: %s\n", workerID, task.ID, task.Payload)
	time.Sleep(100 * time.Millisecond) // Simulate work
}

func (p *WorkerPool) Submit(task Task) bool {
	select {
	case p.taskQueue <- task:
		return true
	default:
		return false // Queue is full
	}
}

func (p *WorkerPool) Stop() {
	close(p.taskQueue)
	p.wg.Wait()
}
