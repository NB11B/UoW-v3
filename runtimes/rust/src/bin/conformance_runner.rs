//! Conformance runner CLI for canonical UoW test vectors in Rust.

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process;
use uow_runtime::engine::TransitionEngine;

fn run_single_vector(path: &Path) -> Result<serde_json::Value, String> {
    let content = fs::read_to_string(path)
        .map_err(|e| format!("Failed to read file {}: {}", path.display(), e))?;
    let vector_json: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse JSON {}: {}", path.display(), e))?;

    let mut engine = TransitionEngine::new();
    let result = engine.dispatch_vector(&vector_json);
    Ok(result)
}

fn run_batch_all(dir: &Path) -> (usize, usize) {
    let mut files: Vec<PathBuf> = fs::read_dir(dir)
        .expect("Failed to read vectors directory")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("json"))
        .collect();

    files.sort();

    let total = files.len();
    let mut passed = 0;
    let mut engine = TransitionEngine::new();

    for file in &files {
        let filename = file.file_name().unwrap().to_str().unwrap();
        let stem = file.file_stem().unwrap().to_str().unwrap();
        let prefix = if stem.len() >= 3 { &stem[0..3] } else { stem };

        let content = match fs::read_to_string(file) {
            Ok(c) => c,
            Err(e) => {
                println!("{} FAIL: {}", prefix, e);
                continue;
            }
        };

        let vector_json: serde_json::Value = match serde_json::from_str(&content) {
            Ok(v) => v,
            Err(e) => {
                println!("{} FAIL: JSON parse error: {}", prefix, e);
                continue;
            }
        };

        let expected = match vector_json.get("expected") {
            Some(e) => e,
            None => {
                println!("{} FAIL: Missing 'expected'", prefix);
                continue;
            }
        };

        let actual = engine.dispatch_vector(&vector_json);

        let exp_status = expected.get("status").and_then(|s| s.as_str()).unwrap_or("");
        let act_status = actual.get("status").and_then(|s| s.as_str()).unwrap_or("");

        if exp_status != act_status {
            println!(
                "{} FAIL: status mismatch (expected {}, got {})",
                prefix, exp_status, act_status
            );
            continue;
        }

        if filename == "005_evidence_chain_continuity.json" {
            let exp_len = expected.get("ledger_length").and_then(|l| l.as_u64()).unwrap_or(0);
            let act_len = actual.get("ledger_length").and_then(|l| l.as_u64()).unwrap_or(0);
            let exp_integ = expected.get("ledger_integrity").and_then(|b| b.as_bool()).unwrap_or(false);
            let act_integ = actual.get("ledger_integrity").and_then(|b| b.as_bool()).unwrap_or(false);

            if exp_len != act_len || exp_integ != act_integ {
                println!(
                    "{} FAIL: evidence ledger mismatch (len: {} vs {}, integrity: {} vs {})",
                    prefix, exp_len, act_len, exp_integ, act_integ
                );
                continue;
            }
        }

        println!("{} PASS", prefix);
        passed += 1;
    }

    println!("\nRust semantic conformance: {}/{}", passed, total);
    (passed, total)
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: conformance_runner [--all <dir> | <vector_file.json>]");
        process::exit(1);
    }

    if args[1] == "--all" {
        if args.len() < 3 {
            eprintln!("Error: --all requires vectors directory path");
            process::exit(1);
        }
        let dir = Path::new(&args[2]);
        let (passed, total) = run_batch_all(dir);
        if passed == total && total >= 16 {
            process::exit(0);
        } else {
            process::exit(1);
        }
    } else {
        let file_path = Path::new(&args[1]);
        match run_single_vector(file_path) {
            Ok(res) => {
                println!("{}", serde_json::to_string_pretty(&res).unwrap());
                process::exit(0);
            }
            Err(e) => {
                eprintln!("Error: {}", e);
                process::exit(1);
            }
        }
    }
}
