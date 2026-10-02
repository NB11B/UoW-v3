$ErrorActionPreference = "Stop"

# Ensure local venv (if present) and repository src are prioritized
$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
if (Test-Path "$repoRoot\.venv\Scripts") {
    $env:PATH = "$repoRoot\.venv\Scripts;$env:PATH"
}
$env:PYTHONPATH = "$repoRoot\src;$env:PYTHONPATH"

Write-Host "=== 1. Python Pytest Regression ===" -ForegroundColor Cyan
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed with code $LASTEXITCODE" }

Write-Host "`n=== 2. Rust Protocol SDK ===" -ForegroundColor Cyan
cargo test --manifest-path sdk/rust/Cargo.toml
if ($LASTEXITCODE -ne 0) { throw "cargo test sdk/rust failed with code $LASTEXITCODE" }

Write-Host "`n=== 3. Rust Native Runtime ===" -ForegroundColor Cyan
cargo test --manifest-path runtimes/rust/Cargo.toml
if ($LASTEXITCODE -ne 0) { throw "cargo test runtimes/rust failed with code $LASTEXITCODE" }

Write-Host "`n=== 4. TypeScript Reference SDK & Conformance ===" -ForegroundColor Cyan
npm test --prefix sdk/typescript
if ($LASTEXITCODE -ne 0) { throw "npm test failed with code $LASTEXITCODE" }

Write-Host "`n=== 5. Perl Adapter Conformance ===" -ForegroundColor Cyan
C:\Strawberry\perl\bin\perl.exe `
    -I adapters/perl `
    adapters/perl/t/conformance.t
if ($LASTEXITCODE -ne 0) { throw "perl conformance failed with code $LASTEXITCODE" }

Write-Host "`n=== 6. Native C++ Conformance Runner ===" -ForegroundColor Cyan
C:\Strawberry\c\bin\g++.exe `
    -std=c++17 `
    -I runtimes/cpp/include `
    runtimes/cpp/native_state.cpp `
    runtimes/cpp/native_evidence.cpp `
    runtimes/cpp/native_idempotency.cpp `
    runtimes/cpp/native_protocol.cpp `
    runtimes/cpp/conformance_runner.cpp `
    -o runtimes/cpp/conformance_runner.exe
if ($LASTEXITCODE -ne 0) { throw "g++ compilation failed with code $LASTEXITCODE" }

.\runtimes\cpp\conformance_runner.exe --all conformance\vectors
if ($LASTEXITCODE -ne 0) { throw "C++ conformance runner failed with code $LASTEXITCODE" }

Remove-Item runtimes\cpp\conformance_runner.exe -Force

Write-Host "`n=== 7. Verify Minimal Public API ===" -ForegroundColor Cyan
$apiOutput = python -c "import uow; print(uow.__all__)"
Write-Host $apiOutput
$expectedApi = "['UoW', 'WorldState', 'execute', 'authority', 'runtime', 'autonomy', 'semantic', 'economics', 'protocol', 'adapters']"
if ($apiOutput.Trim() -ne $expectedApi) {
    throw "Minimal API mismatch: expected $expectedApi, got $apiOutput"
}

Write-Host "`n================================================" -ForegroundColor Green
Write-Host "All UoW v3.1 Release Gates Successfully Passed!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
