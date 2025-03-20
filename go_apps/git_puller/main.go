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
var skipDirs = []string{"personal_credentials", "hellofresh_credentials", "na-finops", "na-faba", "na-fin-data-streamlit", "FABA_Final_Project"}

// Run `git pull` on a repo and capture results
func gitPull(repo string, wg *sync.WaitGroup, results chan<- string, errors chan<- string, verbose bool) {
	defer wg.Done()

	absRepo, err := filepath.Abs(repo)
	if err != nil {
		errors <- fmt.Sprintf("[ERROR] Failed to resolve path: %s", repo)
		return
	}

	if verbose {
		fmt.Println("[STARTING] Pulling repo:", absRepo)
	}

	cmd := exec.Command("git", "-C", absRepo, "pull")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()
	output := strings.TrimSpace(stdout.String())
	errorMsg := strings.TrimSpace(stderr.String())

	// Detect authentication failure
	if strings.Contains(errorMsg, "Username for 'https://github.com'") || strings.Contains(errorMsg, "fatal: could not read Username") {
		errors <- fmt.Sprintf("[AUTH REQUIRED] %s (Skipping)", absRepo)
		return
	}

	// Log other Git errors
	if err != nil {
		errors <- fmt.Sprintf("[FAILED] %s: %s", absRepo, errorMsg)
		return
	}

	// Log successful results
	if output == "Already up to date." {
		results <- fmt.Sprintf("[NO CHANGES] %s", absRepo)
	} else {
		results <- fmt.Sprintf("[UPDATED] %s:\n%s", absRepo, output)
	}

	if verbose {
		fmt.Println("[DONE] Finished pulling repo:", absRepo)
	}
}

// Find all Git repositories in a directory with a specified depth
func findGitRepos(baseDir string, maxDepth int, skipped *[]string, notGitRepos *[]string, verbose bool) []string {
	var repos []string
	baseDepth := strings.Count(baseDir, string(filepath.Separator))

	if verbose {
		fmt.Println("[SCANNING] Searching for Git repositories in:", baseDir)
	}

	err := filepath.Walk(baseDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			fmt.Println("[ERROR] Accessing:", path, err)
			return nil
		}

		absPath, _ := filepath.Abs(path)

		// Skip explicitly listed directories
		if contains(skipDirs, filepath.Base(path)) {
			*skipped = append(*skipped, fmt.Sprintf("[SKIPPED] %s (In skip list)", absPath))
			return filepath.SkipDir
		}

		// Ignore non-directory files
		if !info.IsDir() {
			return nil
		}

		// Check if this is a Git repo before applying depth limit
		if isGitRepo(path) {
			if verbose {
				fmt.Println("[FOUND] Git repo detected:", absPath)
			}
			repos = append(repos, absPath)
			return filepath.SkipDir // Stop scanning inside this repo
		}

		// If it's a directory and not a Git repo, log it
		*notGitRepos = append(*notGitRepos, fmt.Sprintf("[NOT A REPO] %s", absPath))

		// Enforce depth limit for non-Git directories
		currentDepth := strings.Count(path, string(filepath.Separator))
		if maxDepth > 0 && (currentDepth-baseDepth) >= maxDepth {
			if verbose {
				fmt.Println("[DEPTH LIMIT] Stopping at:", absPath)
			}
			return filepath.SkipDir
		}

		return nil
	})

	if err != nil {
		fmt.Println("[ERROR] Failed to scan directory:", baseDir, err)
	}

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
	verbose := flag.Bool("v", false, "Enable verbose output (logs when starting/ending a repo)")
	depth := flag.Int("depth", 1, "Recursion depth when using -r (default: 1, -1 for unlimited)")
	flag.Parse()

	if len(repoPaths) == 0 {
		fmt.Println("[ERROR] Please provide at least one path using -path")
		os.Exit(1)
	}

	var repos []string
	var skipped []string
	var notGitRepos []string

	for _, path := range repoPaths {
		absPath, err := filepath.Abs(path)
		if err != nil {
			fmt.Println("[ERROR] Invalid path:", path)
			continue
		}

		stat, err := os.Stat(path)
		if err != nil {
			fmt.Println("[ERROR] Invalid path:", absPath)
			continue
		}

		if contains(skipDirs, filepath.Base(absPath)) {
			skipped = append(skipped, fmt.Sprintf("[SKIPPED] %s (In skip list)", absPath))
			continue
		}

		if stat.IsDir() {
			if *recursive {
				foundRepos := findGitRepos(absPath, *depth, &skipped, &notGitRepos, *verbose)
				repos = append(repos, foundRepos...)
			} else if isGitRepo(absPath) {
				repos = append(repos, absPath)
			} else {
				notGitRepos = append(notGitRepos, fmt.Sprintf("[NOT A REPO] %s", absPath))
			}
		} else {
			fmt.Println("[ERROR] Skipping non-directory:", absPath)
		}
	}

	// Run Git pull on valid repos first before printing skipped
	var wg sync.WaitGroup
	results := make(chan string, len(repos))
	errors := make(chan string, len(repos))

	for _, repo := range repos {
		wg.Add(1)
		go gitPull(repo, &wg, results, errors, *verbose)
	}

	wg.Wait()
	close(results)
	close(errors)

	// Print everything in the correct order
	fmt.Println("\n=== Skipped Directories ===")
	for _, skip := range skipped {
		fmt.Println(skip)
	}

	fmt.Println("\n=== Not a Git Repo ===")
	for _, notRepo := range notGitRepos {
		fmt.Println(notRepo)
	}

	fmt.Println("\n=== Pull Results ===")
	for res := range results {
		fmt.Println(res)
	}

	fmt.Println("\n=== Errors ===")
	for err := range errors {
		fmt.Println(err)
	}
}
