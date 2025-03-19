package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
)

// List of directories to skip
var skipDirs = []string{"skip_this_repo", "ignore_this_one"}

// Run `git pull` on a repo and capture results
func gitPull(repo string, wg *sync.WaitGroup, results chan<- string, errors chan<- string) {
	defer wg.Done()

	cmd := exec.Command("git", "-C", repo, "pull")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		errors <- fmt.Sprintf("[FAILED] %s: %s", repo, strings.TrimSpace(stderr.String()))
		return
	}

	output := strings.TrimSpace(stdout.String())
	if output == "Already up to date." {
		results <- fmt.Sprintf("[NO CHANGES] %s", repo)
	} else {
		results <- fmt.Sprintf("[UPDATED] %s:\n%s", repo, output)
	}
}

// Detect all repos recursively in a given directory
func findGitRepos(baseDir string) []string {
	var repos []string
	filepath.Walk(baseDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		// Skip explicitly listed directories
		if contains(skipDirs, filepath.Base(path)) {
			return filepath.SkipDir
		}
		// Check if this is a git repo
		if info.IsDir() && isGitRepo(path) {
			repos = append(repos, path)
		}
		return nil
	})
	return repos
}

// Check if a directory is a Git repo
func isGitRepo(path string) bool {
	_, err := os.Stat(filepath.Join(path, ".git"))
	return err == nil
}

// Helper function to check if a string is in a slice
func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

func main() {
	// Accept arguments: path to repos and a recursive flag
	repoPath := flag.String("path", "", "Path to a repo, multiple space-separated repos, or a directory")
	recursive := flag.Bool("r", false, "Enable recursive search for git repos in the directory")
	flag.Parse()

	if *repoPath == "" {
		fmt.Println("[ERROR] Please provide a path using -path")
		os.Exit(1)
	}

	var repos []string
	stat, err := os.Stat(*repoPath)
	if err != nil {
		fmt.Println("[ERROR] Invalid path:", *repoPath)
		os.Exit(1)
	}

	if stat.IsDir() {
		if *recursive {
			// Recursive directory search
			repos = findGitRepos(*repoPath)
		} else if isGitRepo(*repoPath) {
			// Single Git repo case
			repos = append(repos, *repoPath)
		} else {
			fmt.Println("[ERROR] Provided directory is not a git repo. Use -r for recursive search.")
			os.Exit(1)
		}
	} else {
		// Treat as space-separated list
		repos = strings.Fields(*repoPath)
	}

	if len(repos) == 0 {
		fmt.Println("[ERROR] No valid Git repos found")
		os.Exit(1)
	}

	// Prepare channels for results
	var wg sync.WaitGroup
	results := make(chan string, len(repos))
	errors := make(chan string, len(repos))
	skipped := make(chan string, len(repos))

	for _, repo := range repos {
		repoName := filepath.Base(repo)

		// Skip explicitly listed directories
		if contains(skipDirs, repoName) {
			skipped <- fmt.Sprintf("[SKIPPED] %s (In skip list)", repoName)
			continue
		}

		// Skip non-git directories
		if !isGitRepo(repo) {
			skipped <- fmt.Sprintf("[SKIPPED] %s (Not a git repo)", repoName)
			continue
		}

		wg.Add(1)
		go gitPull(repo, &wg, results, errors)
	}

	wg.Wait()
	close(results)
	close(errors)
	close(skipped)

	fmt.Println("=== Pull Results ===")
	for res := range results {
		fmt.Println(res)
	}

	fmt.Println("\n=== Errors ===")
	for err := range errors {
		fmt.Println(err)
	}

	fmt.Println("\n=== Skipped ===")
	for skip := range skipped {
		fmt.Println(skip)
	}
}
