//! Deterministic DAG orchestration, dependency tracking, and cycle defense.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DagError {
    CycleDetected,
    DependencyViolation(String),
    DuplicateCompletion(String),
    MissingNode(String),
    InvalidState(String),
}

impl std::fmt::Display for DagError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DagError::CycleDetected => write!(f, "Cycle detected in DAG"),
            DagError::DependencyViolation(msg) => write!(f, "Dependency violation: {}", msg),
            DagError::DuplicateCompletion(task) => write!(f, "Duplicate completion for task: {}", task),
            DagError::MissingNode(task) => write!(f, "Task not found in DAG: {}", task),
            DagError::InvalidState(msg) => write!(f, "Invalid state transition: {}", msg),
        }
    }
}

impl std::error::Error for DagError {}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationDAG {
    pub nodes: BTreeSet<String>,
    pub dependencies: BTreeMap<String, BTreeSet<String>>,
    pub queue: BTreeSet<String>,
    pub active: BTreeSet<String>,
    pub completed: BTreeSet<String>,
}

impl OrchestrationDAG {
    pub fn new() -> Self {
        Self {
            nodes: BTreeSet::new(),
            dependencies: BTreeMap::new(),
            queue: BTreeSet::new(),
            active: BTreeSet::new(),
            completed: BTreeSet::new(),
        }
    }

    /// Construct a DAG from an array of (task_id, [dependencies])
    pub fn from_definitions(tasks: &[(&str, &[&str])]) -> Result<Self, DagError> {
        let mut dag = Self::new();
        for (task, deps) in tasks {
            dag.add_task(task, deps)?;
        }
        Ok(dag)
    }

    pub fn add_task(&mut self, task: &str, deps: &[&str]) -> Result<(), DagError> {
        self.nodes.insert(task.to_string());
        self.queue.insert(task.to_string());

        let mut dep_set = BTreeSet::new();
        for d in deps {
            self.nodes.insert(d.to_string());
            if !self.completed.contains(*d) && !self.active.contains(*d) {
                self.queue.insert(d.to_string());
            }
            dep_set.insert(d.to_string());
        }
        self.dependencies.insert(task.to_string(), dep_set);

        if self.has_cycle() {
            // Revert insertion on cycle detection
            self.nodes.remove(task);
            self.queue.remove(task);
            self.dependencies.remove(task);
            return Err(DagError::CycleDetected);
        }

        Ok(())
    }

    /// Check for cycles in the dependency graph using DFS
    pub fn has_cycle(&self) -> bool {
        let mut visited = BTreeMap::new(); // 0: unvisited, 1: visiting, 2: visited
        for node in &self.nodes {
            visited.insert(node.as_str(), 0);
        }

        fn dfs<'a>(
            node: &'a str,
            deps: &'a BTreeMap<String, BTreeSet<String>>,
            visited: &mut BTreeMap<&'a str, i32>,
        ) -> bool {
            visited.insert(node, 1);
            if let Some(node_deps) = deps.get(node) {
                for dep in node_deps {
                    let state = visited.get(dep.as_str()).copied().unwrap_or(0);
                    if state == 1 {
                        return true; // Cycle found
                    }
                    if state == 0 && dfs(dep.as_str(), deps, visited) {
                        return true;
                    }
                }
            }
            visited.insert(node, 2);
            false
        }

        for node in &self.nodes {
            if visited.get(node.as_str()).copied().unwrap_or(0) == 0 {
                if dfs(node.as_str(), &self.dependencies, &mut visited) {
                    return true;
                }
            }
        }
        false
    }

    /// Get all tasks currently in queue whose dependencies are completely satisfied
    pub fn eligible_tasks(&self) -> Vec<String> {
        let mut eligible = Vec::new();
        for task in &self.queue {
            let task_deps = self.dependencies.get(task);
            let ready = match task_deps {
                Some(deps) => deps.iter().all(|d| self.completed.contains(d)),
                None => true,
            };
            if ready {
                eligible.push(task.clone());
            }
        }
        eligible.sort(); // Deterministic ordering
        eligible
    }

    /// Dispatch a ready task into the active execution set
    pub fn dispatch_task(&mut self, task: &str) -> Result<(), DagError> {
        if !self.nodes.contains(task) {
            return Err(DagError::MissingNode(task.to_string()));
        }
        if !self.queue.contains(task) {
            return Err(DagError::InvalidState(format!(
                "Task '{}' is not pending in queue",
                task
            )));
        }

        // Verify dependencies are all completed
        if let Some(deps) = self.dependencies.get(task) {
            for dep in deps {
                if !self.completed.contains(dep) {
                    return Err(DagError::DependencyViolation(format!(
                        "Task '{}' requires uncompleted dependency '{}'",
                        task, dep
                    )));
                }
            }
        }

        self.queue.remove(task);
        self.active.insert(task.to_string());
        Ok(())
    }

    /// Mark an active task completed
    pub fn complete_task(&mut self, task: &str) -> Result<(), DagError> {
        if !self.nodes.contains(task) {
            return Err(DagError::MissingNode(task.to_string()));
        }
        if self.completed.contains(task) {
            return Err(DagError::DuplicateCompletion(task.to_string()));
        }
        if !self.active.contains(task) {
            return Err(DagError::InvalidState(format!(
                "Task '{}' is not currently active",
                task
            )));
        }

        self.active.remove(task);
        self.completed.insert(task.to_string());
        Ok(())
    }

    /// Determine if the DAG has finished all work
    pub fn is_halted(&self) -> bool {
        self.queue.is_empty() && self.active.is_empty() && self.completed.len() == self.nodes.len()
    }
}
