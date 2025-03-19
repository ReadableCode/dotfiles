package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
)

// List of directories to skip
var skipDirs = []string{"server_configs"}

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
	// Accept multiple paths with -path flag
	var repoPaths []string
	flag.Func("path", "Specify one or more paths to repos (space-separated or multiple -path flags)", func(s string) error {
		if runtime.GOOS == "windows" {
			repoPaths = append(repoPaths, strings.Split(s, ";")...) // Handle Windows `;` separation
		} else {
			repoPaths = append(repoPaths, strings.Fields(s)...) // Handle Linux/macOS space-separated paths
		}
		return nil
	})

	recursive := flag.Bool("r", false, "Enable recursive search for git repos in the directory")
	flag.Parse()

	if len(repoPaths) == 0 {
		fmt.Println("[ERROR] Please provide at least one path using -path")
		os.Exit(1)
	}

	var repos []string
	notGitRepos := make(chan string, len(repoPaths))

	for _, path := range repoPaths {
		stat, err := os.Stat(path)
		if err != nil {
			fmt.Println("[ERROR] Invalid path:", path)
			continue
		}

		if stat.IsDir() {
			if *recursive {
				// Recursive directory search
				repos = append(repos, findGitRepos(path)...)
			} else if isGitRepo(path) {
				// Single Git repo case
				repos = append(repos, path)
			} else {
				notGitRepos <- path
			}
		} else {
			fmt.Println("[ERROR] Skipping non-directory:", path)
		}
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
	close(notGitRepos)

	// Output results
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

	fmt.Println("\n=== Not a Git Repo ===")
	for notRepo := range notGitRepos {
		fmt.Println(notRepo)
	}
}
